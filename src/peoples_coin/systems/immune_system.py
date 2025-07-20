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
    Immune System: security layer for Flask apps.
    - Rate limiting
    - Greylisting (temporary deny)
    - Blacklisting (permanent deny)
    Uses Redis if available, else in-memory fallback.
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
        """Initializes the Immune System with Flask app config."""
        if self._initialized:
            logger.warning("🛡️ ImmuneSystem already initialized.")
            return

        self.app = app
        self.config = app.config

        # Default configs
        self.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        self.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        self.config.setdefault("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        self.config.setdefault("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        self.config.setdefault("REDIS_URL", "redis://localhost:6379/1")
        self.config.setdefault("REDIS_CONNECT_RETRIES", 3)
        self.config.setdefault("REDIS_CONNECT_BACKOFF_SEC", 1)

        self._connect_redis()
        self._start_cleaner()
        self._initialized = True
        logger.info("🛡️ ImmuneSystem initialized.")

    def _connect_redis(self):
        """Connects to Redis with retries."""
        if Redis is None:
            logger.warning("🛡️ Redis library not installed; fallback to memory.")
            return

        with self._redis_lock:
            for attempt in range(1, self.config["REDIS_CONNECT_RETRIES"] + 1):
                try:
                    redis_client = Redis.from_url(
                        self.config["REDIS_URL"], decode_responses=True,
                        socket_connect_timeout=1, socket_timeout=1
                    )
                    redis_client.ping()
                    self.redis = redis_client
                    logger.info(f"🛡️ Connected to Redis (attempt {attempt}).")
                    return
                except (RedisExceptions.RedisError, ValueError) as e:
                    logger.warning(f"🛡️ Redis attempt {attempt} failed: {e}")
                    time.sleep(self.config["REDIS_CONNECT_BACKOFF_SEC"])

            logger.warning("🛡️ Redis unavailable after retries; fallback to memory.")
            self.redis = None

    def _get_identifier(self) -> str:
        """Returns a unique identifier for the client."""
        if hasattr(g, "user_id") and g.user_id:
            return f"user:{g.user_id}"
        if (api_key := request.headers.get("X-API-Key")):
            return f"api_key:{api_key}"
        return f"ip:{request.remote_addr or 'unknown'}"

    def is_blacklisted(self, identifier: str) -> bool:
        """Check if client is blacklisted."""
        if self.redis:
            try:
                return self.redis.sismember("immune:blacklist", identifier)
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis error in is_blacklisted; fallback.")
        with self._in_memory_lock:
            return identifier in self._blacklist

    def add_to_blacklist(self, identifier: str):
        """Add client to blacklist."""
        if self.redis:
            try:
                self.redis.sadd("immune:blacklist", identifier)
                logger.info(f"🛡️ Blacklisted {identifier} (Redis).")
                return
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis error adding to blacklist.")
        with self._in_memory_lock:
            self._blacklist.add(identifier)
            logger.info(f"🛡️ Blacklisted {identifier} (memory).")

    def record_invalid_attempt(self, identifier: str):
        """Track failed attempt; blacklist if threshold exceeded."""
        if self.is_blacklisted(identifier):
            return

        max_attempts = self.config["IMMUNE_MAX_INVALID_ATTEMPTS"]
        quarantine = self.config["IMMUNE_QUARANTINE_TIME_SEC"]

        if self.redis:
            try:
                key = f"immune:greylist:{identifier}"
                count = self.redis.incr(key)
                self.redis.expire(key, quarantine)
                if count >= max_attempts:
                    self.add_to_blacklist(identifier)
                    self.redis.delete(key)
                return
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis error in record_invalid_attempt.")

        with self._in_memory_lock:
            entry = self._greylist[identifier]
            entry["count"] += 1
            entry["last_seen"] = time.time()
            if entry["count"] >= max_attempts:
                self.add_to_blacklist(identifier)
                del self._greylist[identifier]

    def _is_rate_limited(self, identifier: str) -> bool:
        """Check if rate limit exceeded."""
        if self.redis:
            try:
                key = f"immune:rate_limit:{identifier}"
                p = self.redis.pipeline()
                p.incr(key)
                p.expire(key, self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"])
                count, _ = p.execute()
                return count > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis error in rate limit check.")

        now = time.time()
        window = now - self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"]
        with self._in_memory_lock:
            self._rate_limits[identifier] = [
                ts for ts in self._rate_limits[identifier] if ts > window
            ] + [now]
            return len(self._rate_limits[identifier]) > self.config["IMMUNE_MAX_REQUESTS_PER_WINDOW"]

    def check(self) -> Callable:
        """Flask route decorator applying immune checks."""
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def wrapper(*args, **kwargs):
                identifier = self._get_identifier()

                if self.is_blacklisted(identifier):
                    logger.warning(f"🛡️ Blocked {identifier} (blacklisted).")
                    return jsonify({"error": "Access denied"}), http.HTTPStatus.FORBIDDEN

                if self._is_rate_limited(identifier):
                    logger.warning(f"🛡️ Blocked {identifier} (rate limit).")
                    return jsonify({"error": "Too many requests"}), http.HTTPStatus.TOO_MANY_REQUESTS

                return f(*args, **kwargs)
            return wrapper
        return decorator

    def _cleaner_task(self):
        """Cleans in-memory greylist/rate-limits (fallback only)."""
        logger.info("🛡️ Cleaner thread started.")
        while not self._stop_event.is_set():
            try:
                if not self.redis:
                    now = time.time()
                    quarantine = self.config.get("IMMUNE_QUARANTINE_TIME_SEC", 300)
                    window = self.config.get("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)

                    with self._in_memory_lock:
                        self._greylist = defaultdict(
                            lambda: {"count": 0, "last_seen": 0},
                            {
                                k: v for k, v in self._greylist.items()
                                if now - v["last_seen"] <= quarantine
                            }
                        )
                        self._rate_limits = defaultdict(
                            list,
                            {
                                k: [ts for ts in v if ts > now - window]
                                for k, v in self._rate_limits.items()
                                if any(ts > now - window for ts in v)
                            }
                        )

                self._stop_event.wait(600)  # sleep 10 minutes
            except Exception as e:
                logger.error(f"🛡️ Cleaner thread error: {e}", exc_info=True)
        logger.info("🛡️ Cleaner thread stopped.")

    def _start_cleaner(self):
        """Starts the cleaner thread."""
        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(
                target=self._cleaner_task, daemon=True, name="ImmuneCleaner"
            )
            self._cleaner_thread.start()

    def stop(self):
        """Stops the cleaner thread gracefully."""
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            logger.info("🛡️ Stopping cleaner thread...")
            self._stop_event.set()
            self._cleaner_thread.join(timeout=10)

    def status(self) -> Dict[str, Any]:
        """Returns current immune system state summary."""
        with self._in_memory_lock:
            redis_bl, redis_gl = 0, 0
            if self.redis:
                try:
                    redis_bl = self.redis.scard("immune:blacklist") or 0
                    redis_gl = len(self.redis.keys("immune:greylist:*"))
                except Exception as e:
                    logger.warning(f"🛡️ Error fetching Redis state: {e}")
            return {
                "redis_connected": self.redis is not None,
                "blacklist_size": redis_bl if self.redis else len(self._blacklist),
                "greylist_size": redis_gl if self.redis else len(self._greylist),
                "cleaner_running": self._cleaner_thread.is_alive() if self._cleaner_thread else False,
            }


# Singleton
immune_system = ImmuneSystem()

def start_immune_system_cleaner():
    immune_system._start_cleaner()

def stop_immune_system_cleaner():
    immune_system.stop()

_cleaner_thread = immune_system._cleaner_thread

