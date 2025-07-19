import os
import time
import threading
import logging
import http
from functools import wraps
from collections import defaultdict
from typing import Optional, Callable, Dict, Any

from flask import request, jsonify, Flask, g

try:
    from redis import Redis, exceptions as RedisExceptions
except ImportError:
    Redis = None
    RedisExceptions = None

logger = logging.getLogger(__name__)


class ImmuneSystem:
    """
    Stateful security layer for Flask apps providing:
    - Rate limiting
    - Greylisting (failed attempts tracking)
    - Blacklisting (permanent or semi-permanent)
    Uses Redis backend if available, else in-memory fallback.
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
            logger.warning("🛡️ ImmuneSystem already initialized.")
            return

        self.app = app
        self.config = app.config

        # Set default config values if not present
        self.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        self.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        self.config.setdefault("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        self.config.setdefault("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        self.config.setdefault("REDIS_URL", self.config.get("REDIS_URI", "redis://localhost:6379/1"))
        self.config.setdefault("REDIS_CONNECT_RETRIES", 3)
        self.config.setdefault("REDIS_CONNECT_BACKOFF_SEC", 1)

        self._lazy_connect_redis()
        self._start_cleaner()
        self._initialized = True
        logger.info("🛡️ ImmuneSystem initialized.")

    def _lazy_connect_redis(self):
        """Tries to connect to Redis with retries and backoff."""
        if Redis is None:
            logger.warning("🛡️ Redis library not installed, using in-memory fallback.")
            return

        if self.redis is not None:
            return  # Already connected

        with self._redis_lock:
            if self.redis is not None:
                return

            for attempt in range(1, self.config["REDIS_CONNECT_RETRIES"] + 1):
                try:
                    redis_client = Redis.from_url(
                        self.config["REDIS_URL"], decode_responses=True,
                        socket_connect_timeout=1, socket_timeout=1
                    )
                    redis_client.ping()
                    self.redis = redis_client
                    logger.info(f"🛡️ Connected to Redis on attempt {attempt}.")
                    return
                except (RedisExceptions.RedisError, ValueError) as e:
                    logger.warning(f"🛡️ Redis connection attempt {attempt} failed: {e}")
                    time.sleep(self.config["REDIS_CONNECT_BACKOFF_SEC"])

            logger.warning("🛡️ Redis unavailable after retries, falling back to in-memory.")
            self.redis = None

    def _get_identifier(self) -> str:
        """
        Unique identifier for the requestor.
        Prefers authenticated user ID from Flask 'g', then API key, then IP address.
        """
        if hasattr(g, "user_id") and g.user_id:
            return f"user:{g.user_id}"

        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"

        if request:
            return f"ip:{request.remote_addr}"

        return "background_task"

    def is_blacklisted(self, identifier: str) -> bool:
        """Checks if the identifier is blacklisted (permanent deny)."""
        if self.redis:
            try:
                return self.redis.sismember("immune:blacklist", identifier)
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error in is_blacklisted: {e}, falling back to in-memory.")

        with self._in_memory_lock:
            return identifier in self._blacklist

    def add_to_blacklist(self, identifier: str):
        """Manually add an identifier to blacklist."""
        if self.redis:
            try:
                self.redis.sadd("immune:blacklist", identifier)
                logger.info(f"🛡️ Added {identifier} to Redis blacklist.")
                return
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error adding to blacklist: {e}, falling back to in-memory.")

        with self._in_memory_lock:
            self._blacklist.add(identifier)
            logger.info(f"🛡️ Added {identifier} to in-memory blacklist.")

    def remove_from_blacklist(self, identifier: str):
        """Removes an identifier from the blacklist."""
        if self.redis:
            try:
                self.redis.srem("immune:blacklist", identifier)
                logger.info(f"🛡️ Removed {identifier} from Redis blacklist.")
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error removing from blacklist: {e}")

        with self._in_memory_lock:
            self._blacklist.discard(identifier)
            logger.info(f"🛡️ Removed {identifier} from in-memory blacklist.")

    def record_invalid_attempt(self, identifier: str):
        """Records a failed attempt; blacklists if max attempts exceeded."""
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
                    self.add_to_blacklist(identifier)
                    self.redis.delete(key)
                    logger.warning(f"🛡️ Blacklisted {identifier} via Redis (exceeded {max_attempts} invalid attempts).")
                return
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error recording invalid attempt: {e}, falling back to in-memory.")

        with self._in_memory_lock:
            entry = self._greylist[identifier]
            entry["count"] += 1
            entry["last_seen"] = time.time()
            if entry["count"] >= max_attempts:
                self.add_to_blacklist(identifier)
                del self._greylist[identifier]
                logger.warning(f"🛡️ Blacklisted {identifier} in-memory (exceeded {max_attempts} invalid attempts).")

    def _is_rate_limited(self, identifier: str) -> bool:
        """Checks if the identifier has exceeded rate limits."""
        if self.redis:
            try:
                key = f"immune:rate_limit:{identifier}"
                p = self.redis.pipeline()
                p.incr(key, 1)
                p.expire(key, self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"])
                results = p.execute()
                current_count = results[0]
                return current_count > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during rate limit check: {e}, falling back to in-memory.")

        with self._in_memory_lock:
            now = time.time()
            window_start = now - self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"]
            requests = [ts for ts in self._rate_limits[identifier] if ts > window_start]
            requests.append(now)
            self._rate_limits[identifier] = requests
            return len(requests) > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]

    def check(self) -> Callable:
        """
        Flask route decorator applying immune checks:
        - Blacklist block
        - Rate limiting
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
        """Background thread cleaning in-memory greylist and rate limit entries."""
        logger.info("🛡️ ImmuneSystem in-memory cleaner thread started.")
        while not self._stop_event.is_set():
            try:
                if not self.redis:
                    now = time.time()
                    quarantine_time = self.config["IMMUNE_QUARANTINE_TIME_SEC"]
                    with self._in_memory_lock:
                        to_remove = [k for k, v in self._greylist.items() if now - v["last_seen"] > quarantine_time]
                        for k in to_remove:
                            del self._greylist[k]

                        # Clean rate limits older than window
                        window_start = now - self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"]
                        cleaned = {}
                        for k, timestamps in self._rate_limits.items():
                            filtered = [ts for ts in timestamps if ts > window_start]
                            if filtered:
                                cleaned[k] = filtered
                        self._rate_limits = defaultdict(list, cleaned)

                self._stop_event.wait(600)  # Sleep 10 minutes
            except Exception as e:
                logger.error(f"🛡️ ImmuneSystem cleaner thread error: {e}", exc_info=True)
        logger.info("🛡️ ImmuneSystem in-memory cleaner thread exiting.")

    def _start_cleaner(self):
        """Starts the cleaner background thread."""
        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(
                target=self._cleaner_task, daemon=True, name="ImmuneCleaner"
            )
            self._cleaner_thread.start()

    def stop(self):
        """Gracefully stops the cleaner background thread."""
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            logger.info("🛡️ Stopping ImmuneSystem cleaner thread...")
            self._stop_event.set()
            self._cleaner_thread.join(timeout=10)
            if self._cleaner_thread.is_alive():
                logger.warning("🛡️ Cleaner thread did not stop gracefully.")
            else:
                logger.info("🛡️ Cleaner thread stopped.")

    def reset(self, identifier: Optional[str] = None):
        """
        Resets blacklists, greylists, and rate limits.
        If `identifier` provided, resets only for that identifier.
        Note: Redis keys reset is partial; full Redis reset requires careful SCAN+DEL logic.
        """
        with self._in_memory_lock:
            if identifier:
                self._blacklist.discard(identifier)
                self._greylist.pop(identifier, None)
                self._rate_limits.pop(identifier, None)
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
                    logger.info(f"🛡️ Redis data reset for {identifier}")
                else:
                    # WARNING: Full Redis reset not implemented.
                    logger.warning("🛡️ Full Redis reset not implemented; skipping.")
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during reset: {e}")

    def is_cleaner_running(self) -> bool:
        """Checks if the cleaner thread is active."""
        return self._cleaner_thread is not None and self._cleaner_thread.is_alive()

    def status(self) -> Dict[str, Any]:
        """Returns summary of immune system state."""
        with self._in_memory_lock:
            redis_blacklist_count = 0
            redis_greylist_count = 0
            try:
                if self.redis:
                    redis_blacklist_count = self.redis.scard("immune:blacklist") or 0
                    # WARNING: Redis keys() is costly; consider alternative for greylist count in production.
                    greylist_keys = []
                    try:
                        greylist_keys = self.redis.keys("immune:greylist:*")
                    except RedisExceptions.RedisError:
                        greylist_keys = []
                    redis_greylist_count = len(greylist_keys)
            except Exception as e:
                logger.warning(f"🛡️ Error fetching Redis counts: {e}")

            return {
                "redis_connected": self.redis is not None,
                "blacklist_size": redis_blacklist_count if self.redis else len(self._blacklist),
                "greylist_size": redis_greylist_count if self.redis else len(self._greylist),
                "cleaner_running": self.is_cleaner_running(),
            }


# Singleton instance
immune_system = ImmuneSystem()

