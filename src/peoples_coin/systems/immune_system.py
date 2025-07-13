import os
import time
import threading
import logging
import http
from functools import wraps
from collections import defaultdict
from typing import Optional

from flask import request, jsonify, Flask, current_app
from redis import Redis, exceptions as RedisExceptions

logger = logging.getLogger(__name__)

class ImmuneSystem:
    """
    A stateful security layer for Flask applications providing rate-limiting,
    greylisting, and blacklisting with a Redis backend and an in-memory fallback.
    """

    def __init__(self, app: Optional[Flask] = None):
        # Configuration defaults
        self.config = {}
        
        # Redis and state management
        self.redis: Optional[Redis] = None
        self._redis_lock = threading.Lock()

        # In-memory fallback stores
        self._in_memory_lock = threading.Lock()
        self._blacklist = set()
        self._greylist = defaultdict(lambda: {"count": 0, "last_seen": 0})
        self._rate_limits = defaultdict(list)

        # Background cleaner thread management
        self._stop_event = threading.Event()
        self._cleaner_thread: Optional[threading.Thread] = None

        if app:
            self.init_app(app)

    def init_app(self, app: Flask):
        """
        Initializes the Immune System with the Flask app context.
        This follows the standard Flask extension pattern.
        """
        # Default config values
        app.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        app.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        app.config.setdefault("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        app.config.setdefault("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        app.config.setdefault("REDIS_URL", "redis://localhost:6379/1")
        
        self.config = app.config
        
        # The app context teardown is a good place to stop the cleaner
        app.teardown_appcontext(self._teardown)

        self._lazy_connect_redis()
        self._start_cleaner()

    def _lazy_connect_redis(self):
        """Lazily initializes and connects to the Redis client, thread-safe."""
        if self.redis is None:
            with self._redis_lock:
                if self.redis is None:  # Double-check lock
                    logger.info("🛡️ ImmuneSystem: Attempting to connect to Redis...")
                    try:
                        redis_client = Redis.from_url(
                            self.config["REDIS_URL"],
                            decode_responses=True,
                            socket_connect_timeout=1,
                            socket_timeout=1
                        )
                        redis_client.ping()
                        self.redis = redis_client
                        logger.info("🛡️ ImmuneSystem: Successfully connected to Redis.")
                    except (RedisExceptions.ConnectionError, RedisExceptions.TimeoutError, ValueError) as e:
                        logger.warning(f"🛡️ ImmuneSystem: Redis unavailable, falling back to in-memory stores. Error: {e}")
                        self.redis = None

    def _get_identifier(self) -> str:
        """Determines a unique identifier for the requestor: X-User-Id header or IP."""
        if not request:
            return "cli_or_background_task"
        return request.headers.get("X-User-Id") or request.remote_addr or "unknown"

    # --- Blacklisting and Greylisting ---

    def is_blacklisted(self, identifier: str) -> bool:
        """Checks if the identifier is permanently blacklisted."""
        if self.redis:
            try:
                return self.redis.sismember("immune:blacklist", identifier)
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during is_blacklisted check: {e}. Falling back to memory.")
        
        with self._in_memory_lock:
            return identifier in self._blacklist

    def record_invalid_attempt(self, identifier: str):
        """
        Records a failed attempt for an identifier. If attempts exceed the
        configured maximum, the identifier is blacklisted.
        """
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
                    logger.warning(f"🛡️ Blacklisted via Redis: {identifier} after {count} attempts.")
                return
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during record_invalid_attempt: {e}. Falling back to memory.")

        with self._in_memory_lock:
            entry = self._greylist[identifier]
            entry["count"] += 1
            entry["last_seen"] = time.time()
            if entry["count"] >= max_attempts:
                self._blacklist.add(identifier)
                del self._greylist[identifier]
                logger.warning(f"🛡️ Blacklisted in-memory: {identifier} after {entry['count']} attempts.")

    # --- Rate Limiting ---

    def _is_rate_limited(self, identifier: str) -> bool:
        """Checks if the identifier has exceeded the rate limit."""
        if self.redis:
            try:
                key = f"immune:rate_limit:{identifier}"
                p = self.redis.pipeline()
                p.incr(key, 1)
                p.expire(key, self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"])
                request_count = p.execute()[0]
                return request_count > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error during rate limit check: {e}. Falling back to memory.")
        
        # In-memory fallback logic
        with self._in_memory_lock:
            now = time.time()
            window_start = now - self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"]
            
            # Filter out old timestamps
            requests = [ts for ts in self._rate_limits[identifier] if ts > window_start]
            requests.append(now)
            self._rate_limits[identifier] = requests
            
            return len(requests) > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]

    # --- Main Decorator ---

    def check(self):
        """
        Decorator to apply all immune checks (rate limiting & blacklisting) to a route.
        """
        def decorator(f):
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

    # --- Background Cleaner ---

    def _cleaner_task(self):
        """Periodically cleans up in-memory stores if Redis is not used."""
        logger.info("🛡️ ImmuneSystem in-memory cleaner thread started.")
        while not self._stop_event.is_set():
            try:
                if not self.redis:
                    now = time.time()
                    quarantine_time = self.config["IMMUNE_QUARANTINE_TIME_SEC"]
                    with self._in_memory_lock:
                        # Clean greylist
                        to_remove_greylist = [k for k, v in self._greylist.items() if now - v["last_seen"] > quarantine_time]
                        for k in to_remove_greylist:
                            del self._greylist[k]
                        # Note: Rate limit list cleans itself, but we could add a cleanup for idle identifiers
                
                # Wait for 10 minutes or until stop event is set
                self._stop_event.wait(600)
            except Exception as e:
                logger.error(f"🛡️ ImmuneSystem cleaner thread error: {e}", exc_info=True)
        logger.info("🛡️ ImmuneSystem in-memory cleaner thread exiting.")

    def _start_cleaner(self):
        """Starts the background cleaner thread."""
        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(
                target=self._cleaner_task,
                daemon=True,
                name="ImmuneSystemCleaner"
            )
            self._cleaner_thread.start()

    def _teardown(self, exception):
        """Stops the background cleaner thread during app teardown."""
        if self._stop_event.is_set():
            return
        logger.info("🛡️ ImmuneSystem shutting down cleaner thread...")
        self._stop_event.set()
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            # Give the thread a moment to exit gracefully
            self._cleaner_thread.join(timeout=2)

