import os # Import os for config access
import time
import threading
import logging
import http
from functools import wraps
from collections import defaultdict
from typing import Optional, Callable, Dict, Any

from flask import request, jsonify, Flask, g # Import g from Flask

try:
    from redis import Redis, exceptions as RedisExceptions
except ImportError:
    Redis = None
    RedisExceptions = None

logger = logging.getLogger(__name__)


class ImmuneSystem:
    """
    A stateful security layer for Flask applications providing rate-limiting,
    greylisting, and blacklisting with a Redis backend and an in-memory fallback.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self.redis: Optional[Redis] = None
        self._redis_lock = threading.Lock()
        self._in_memory_lock = threading.Lock()
        self._blacklist = set()
        self._greylist = defaultdict(lambda: {"count": 0, "last_seen": 0})
        self._rate_limits = defaultdict(list)
        self._stop_event = threading.Event()
        self._cleaner_thread: Optional[threading.Thread] = None
        self._initialized = False
        logger.info("🫀 ImmuneSystem instance created.")

    def init_app(self, app: Flask):
        """Initializes the Immune System with the Flask app context."""
        if self._initialized:
            return

        self.app = app
        self.config = app.config
        app.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        app.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        app.config.setdefault("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        app.config.setdefault("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        # Use REDIS_URI from app.config (defined in skeleton_system.py Config)
        app.config.setdefault("REDIS_URL", app.config.get("REDIS_URI", "redis://localhost:6379/1"))

        self._lazy_connect_redis()
        self._start_cleaner()
        self._initialized = True
        logger.info("🛡️ ImmuneSystem initialized.")

    def _lazy_connect_redis(self):
        """Lazily connects to the Redis client."""
        if Redis and self.redis is None:
            with self._redis_lock:
                if self.redis is None:
                    try:
                        redis_client = Redis.from_url(
                            self.config["REDIS_URL"], decode_responses=True,
                            socket_connect_timeout=1, socket_timeout=1
                        )
                        redis_client.ping()
                        self.redis = redis_client
                        logger.info("🛡️ ImmuneSystem: Connected to Redis.")
                    except (RedisExceptions.RedisError, ValueError) as e:
                        logger.warning(f"🛡️ Redis unavailable, falling back to in-memory. Error: {e}")
                        self.redis = None

    def _get_identifier(self) -> str:
        """
        Determines a unique identifier for the requestor.
        Prioritizes securely authenticated user IDs (e.g., Firebase UID).
        """
        # CRITICAL: Assuming your authentication middleware stores the authenticated
        #           user's ID (e.g., Firebase UID) in Flask's 'g' object.
        if hasattr(g, 'user_id') and g.user_id:
            return f"user:{g.user_id}" # Prefix with "user:" for clarity
        
        # Fallback for unauthenticated requests or requests with only API keys
        api_key_from_header = request.headers.get("X-API-Key")
        if api_key_from_header:
            return f"api_key:{api_key_from_header}" # Use API Key as identifier

        if request:
            return f"ip:{request.remote_addr}" # Fallback to IP address
        
        return "background_task" # For internal tasks not tied to a request

    def is_blacklisted(self, identifier: str) -> bool:
        """Checks if the identifier is permanently blacklisted."""
        if self.redis:
            try:
                return self.redis.sismember("immune:blacklist", identifier)
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during is_blacklisted: {e}. Falling back.")

        with self._in_memory_lock:
            return identifier in self._blacklist

    def record_invalid_attempt(self, identifier: str):
        """Records a failed attempt, blacklisting if the threshold is met."""
        if self.is_blacklisted(identifier):
            return

        max_attempts = self.config["IMMUNE_MAX_INVALID_ATTEMPTS"]
        quarantine_time = self.config["IMMUNE_QUARANTINE_TIME_SEC"]

        if self.redis:
            try:
                key = f"immune:greylist:{identifier}"
                count = self.redis.incr(key)
                self.redis.expire(key, quarantine_time)
                if count >= max_attempts:
                    self.redis.sadd("immune:blacklist", identifier)
                    self.redis.delete(key)
                    logger.warning(f"🛡️ Blacklisted via Redis: {identifier} (exceeded {max_attempts} attempts).")
                return
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during record_invalid_attempt: {e}. Falling back.")

        with self._in_memory_lock:
            entry = self._greylist[identifier]
            entry["count"] += 1
            entry["last_seen"] = time.time()
            if entry["count"] >= max_attempts:
                self._blacklist.add(identifier)
                del self._greylist[identifier]
                logger.warning(f"🛡️ Blacklisted in-memory: {identifier} (exceeded {max_attempts} attempts).")

    def _is_rate_limited(self, identifier: str) -> bool:
        """Checks if the identifier has exceeded the rate limit."""
        if self.redis:
            try:
                key = f"immune:rate_limit:{identifier}"
                p = self.redis.pipeline()
                p.incr(key, 1)
                p.expire(key, self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"])
                # Compare the *returned count* from incr with MAX_REQUESTS
                return p.execute()[0] > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during rate limit check: {e}. Falling back.")

        with self._in_memory_lock:
            now = time.time()
            window_start = now - self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"]
            # Filter out old requests and add current one
            requests = [ts for ts in self._rate_limits[identifier] if ts > window_start]
            requests.append(now)
            self._rate_limits[identifier] = requests
            return len(requests) > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]

    def check(self) -> Callable:
        """
        Decorator to apply all immune checks to a Flask route.
        Assumes authentication middleware has run and set g.user_id if available.
        """
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def wrapper(*args, **kwargs):
                identifier = self._get_identifier()
                if self.is_blacklisted(identifier):
                    logger.warning(f"🛡️ Blocked blacklisted identifier: {identifier}")
                    return jsonify({"error": "Access permanently denied"}), http.HTTPStatus.FORBIDDEN
                if self._is_rate_limited(identifier):
                    logger.warning(f"🛡️ Rate limit exceeded by identifier: {identifier}")
                    return jsonify({"error": "Too many requests"}), http.HTTPStatus.TOO_MANY_REQUESTS
                return f(*args, **kwargs)
            return wrapper
        return decorator

    def _cleaner_task(self):
        """Periodically cleans up in-memory stores."""
        logger.info("🛡️ ImmuneSystem in-memory cleaner thread started.")
        while not self._stop_event.is_set():
            try:
                if not self.redis: # Only clean in-memory if Redis is not used
                    now = time.time()
                    quarantine_time = self.config["IMMUNE_QUARANTINE_TIME_SEC"]
                    with self._in_memory_lock:
                        to_remove_greylist = [k for k, v in self._greylist.items() if now - v["last_seen"] > quarantine_time]
                        for k in to_remove_greylist:
                            del self._greylist[k]
                        
                        # Clean up rate limits (remove entries older than window)
                        to_clean_rate_limits = {
                            k: [ts for ts in v if ts > (now - self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"])]
                            for k, v in self._rate_limits.items()
                        }
                        self._rate_limits = defaultdict(list, to_clean_rate_limits)

                self._stop_event.wait(600) # Wait for 10 minutes
            except Exception as e:
                logger.error(f"🛡️ ImmuneSystem cleaner thread error: {e}", exc_info=True)
        logger.info("🛡️ ImmuneSystem in-memory cleaner thread exiting.")

    def _start_cleaner(self):
        """Starts the background cleaner thread."""
        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(target=self._cleaner_task, daemon=True, name="ImmuneCleaner")
            self._cleaner_thread.start()

    def stop(self):
        """Stops the background cleaner thread gracefully."""
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            logger.info("🛡️ Stopping ImmuneSystem cleaner thread...")
            self._stop_event.set()
            self._cleaner_thread.join(timeout=10) # Give it 10 seconds to join
            if self._cleaner_thread.is_alive():
                logger.warning("🛡️ Cleaner thread did not stop gracefully.")
            logger.info("🛡️ Cleaner thread stopped.")

    def reset(self, identifier: Optional[str] = None):
        """Resets blacklist and greylist. If identifier is given, resets only for that ID."""
        with self._in_memory_lock:
            if identifier:
                self._blacklist.discard(identifier)
                self._greylist.pop(identifier, None)
                self._rate_limits.pop(identifier, None) # Clear rate limits too
            else:
                self._blacklist.clear()
                self._greylist.clear()
                self._rate_limits.clear()
        if self.redis:
            try:
                if identifier:
                    self.redis.srem("immune:blacklist", identifier)
                    self.redis.delete(f"immune:greylist:{identifier}")
                    self.redis.delete(f"immune:rate_limit:{identifier}")
                else:
                    # Caution: Clearing all Redis keys starting with immune:* requires SCAN + DEL pattern
                    # self.redis.delete("immune:blacklist") # Deletes only that specific set
                    # Implement a more thorough clear if full Redis reset is needed
                    pass
                logger.info("🛡️ ImmuneSystem Redis data reset.")
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during reset: {e}")

    def is_cleaner_running(self) -> bool:
        """Checks if the cleaner thread is active."""
        return self._cleaner_thread is not None and self._cleaner_thread.is_alive()

    def status(self) -> Dict[str, Any]:
        """Returns a summary of the immune system state."""
        with self._in_memory_lock:
            return {
                "redis_connected": self.redis is not None,
                "blacklist_size": (self.redis.scard("immune:blacklist") if self.redis else 0) if self.redis else len(self._blacklist),
                "greylist_size": (self.redis.dbsize() if self.redis and 'immune:greylist:' in self.redis.keys('immune:greylist:*') else 0) if self.redis else len(self._greylist), # More complex Redis count
                "cleaner_running": self.is_cleaner_running()
            }


# Singleton instance
immune_system = ImmuneSystem()
