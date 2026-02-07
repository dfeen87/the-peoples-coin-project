import os
import time
import threading
import logging
import hashlib
import random
from functools import wraps
from collections import defaultdict, deque
from typing import Optional, Callable, Dict, Any
import http

from flask import request, jsonify, Flask, g

try:
    from redis import Redis, exceptions as RedisExceptions
except ImportError:
    Redis = None
    RedisExceptions = None

logger = logging.getLogger(__name__)

class ImmuneSystem:
    """
    Hardened Immune System for Flask apps providing:
    - Rate limiting
    - Blacklisting
    - Greylisting (tracking suspicious attempts)
    - Background cleanup of in-memory stores
    - Optional Redis-backed store for scalability
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self._redis_client: Optional[Redis] = None
        self._redis_lock = threading.Lock()

        # In-memory fallback stores
        self._in_memory_lock = threading.Lock()
        self._blacklist: Dict[str, float] = {}  # identifier -> expiry timestamp
        self._greylist: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "last_seen": 0})
        self._rate_limits: Dict[str, deque[float]] = defaultdict(deque)
        self._pow_cache: Dict[str, float] = {}  # IP -> expiry timestamp for proof-of-work cache

        self._stop_event = threading.Event()
        self._cleaner_thread: Optional[threading.Thread] = None
        self._initialized = False
        logger.info("🫀 ImmuneSystem instance created.")

    def init_app(self, app: Flask):
        """Bind the ImmuneSystem to a Flask app and load config."""
        if self._initialized:
            return
        self.app = app
        self.config = app.config
        self.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        self.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        self.config.setdefault("REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        self.config.setdefault("IMMUNE_BLACKLIST_DECAY_SEC", 3600)
        self.config.setdefault("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        self.config.setdefault("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        self._initialized = True
        logger.info("🛡️ ImmuneSystem configured with Redis URL: %s", self.config["REDIS_URL"])

    @property
    def connection(self) -> Optional[Redis]:
        """Thread-safe lazy Redis connection, fallback to None if unavailable."""
        if Redis is None:
            return None
        if self._redis_client:
            try:
                if self._redis_client.ping():
                    return self._redis_client
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis connection lost, reconnecting...")
                self._redis_client = None
        with self._redis_lock:
            if self._redis_client:
                return self._redis_client
            try:
                client = Redis.from_url(
                    self.config["REDIS_URL"],
                    decode_responses=True,
                    socket_connect_timeout=1,
                )
                client.ping()
                self._redis_client = client
                logger.info("✅ ImmuneSystem connected to Redis.")
                return self._redis_client
            except (RedisExceptions.RedisError, ValueError) as e:
                logger.error(f"🛡️ Redis connect failed: {e}, falling back to in-memory store.")
                return None

    def start(self):
        """Starts background cleaner thread if not running."""
        if not self._initialized:
            logger.warning("ImmuneSystem start() called before initialization.")
            return
        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            logger.info("▶️ Starting ImmuneSystem cleaner thread...")
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(
                target=self._cleaner_task,
                daemon=True,
                name="ImmuneCleaner"
            )
            self._cleaner_thread.start()

    def stop(self):
        """Gracefully stops the cleaner thread."""
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            logger.info("🛑 Stopping ImmuneSystem cleaner thread...")
            self._stop_event.set()
            self._cleaner_thread.join(timeout=5)
            logger.info("✅ ImmuneSystem cleaner thread stopped.")

    def _get_identifier(self) -> str:
        """
        Generate a unique client identifier for tracking.
        Priority: authenticated user ID > API key > IP address
        """
        if hasattr(g, "user") and g.user:
            return f"user:{g.user.id}"
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"
        return f"ip:{request.remote_addr or 'unknown'}"

    def is_blacklisted(self, identifier: str) -> bool:
        """Return True if identifier is currently blacklisted."""
        now = time.time()
        with self._in_memory_lock:
            expiry = self._blacklist.get(identifier)
            if expiry and expiry > now:
                return True
            elif expiry:
                # Expired blacklist entry cleanup
                del self._blacklist[identifier]
        return False

    def add_to_blacklist(self, identifier: str, duration: Optional[int] = None):
        """Blacklist an identifier for `duration` seconds."""
        duration = duration or self.config.get("IMMUNE_BLACKLIST_DECAY_SEC", 3600)
        expiry = time.time() + duration
        with self._in_memory_lock:
            self._blacklist[identifier] = expiry
        logger.warning(f"🛡️ Blacklisted {identifier} for {duration} seconds.")

    def record_invalid_attempt(self, identifier: str):
        """Track a failed attempt, blacklist if threshold exceeded."""
        if self.is_blacklisted(identifier):
            return
        with self._in_memory_lock:
            entry = self._greylist[identifier]
            entry["count"] += 1
            entry["last_seen"] = time.time()
            if entry["count"] >= self.config.get("IMMUNE_MAX_INVALID_ATTEMPTS", 5):
                self.add_to_blacklist(identifier)
                del self._greylist[identifier]
                logger.info(f"🛡️ {identifier} moved from greylist to blacklist due to repeated invalid attempts.")

    def _is_rate_limited(self, identifier: str) -> bool:
        """
        Check if identifier exceeded max requests in sliding time window.
        In-memory only; Redis fallback can be added later.
        """
        max_reqs = self.config.get("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        window = self.config.get("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        now = time.time()
        with self._in_memory_lock:
            timestamps = self._rate_limits[identifier]
            cutoff = now - window
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            timestamps.append(now)
            limited = len(timestamps) > max_reqs
            if limited:
                logger.debug(f"🛡️ Rate limit exceeded for {identifier}: {len(timestamps)} requests in {window} seconds.")
            return limited

    def check(self) -> Callable:
        """
        Flask decorator to protect routes.
        Checks blacklist and rate limits; returns HTTP errors if triggered.
        """
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def wrapper(*args, **kwargs):
                identifier = self._get_identifier()
                if self.is_blacklisted(identifier):
                    logger.warning(f"Access denied for blacklisted identifier: {identifier}")
                    return jsonify({"error": "Access denied"}), http.HTTPStatus.FORBIDDEN
                if self._is_rate_limited(identifier):
                    logger.warning(f"Rate limit exceeded for identifier: {identifier}")
                    return jsonify({"error": "Too many requests"}), http.HTTPStatus.TOO_MANY_REQUESTS
                return f(*args, **kwargs)
            return wrapper
        return decorator

    def _cleaner_task(self):
        """
        Background thread that periodically cleans expired blacklist, greylist, rate limit data.
        Runs every 10 minutes by default.
        """
        logger.info("🛡️ ImmuneSystem cleaner thread started.")
        while not self._stop_event.is_set():
            now = time.time()
            with self._in_memory_lock:
                # Clean expired blacklist entries
                expired_blacklist = [id_ for id_, expiry in self._blacklist.items() if expiry <= now]
                for id_ in expired_blacklist:
                    del self._blacklist[id_]
                    logger.debug(f"🛡️ Removed expired blacklist entry: {id_}")

                # Clean old greylist entries (> quarantine time)
                quarantine = self.config.get("IMMUNE_QUARANTINE_TIME_SEC", 300)
                expired_greylist = [id_ for id_, data in self._greylist.items() if (now - data["last_seen"]) > quarantine]
                for id_ in expired_greylist:
                    del self._greylist[id_]
                    logger.debug(f"🛡️ Removed expired greylist entry: {id_}")

                # Clean old rate limit timestamps outside window
                window = self.config.get("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
                cutoff = now - window
                empty_rate_limits = []
                for id_, timestamps in self._rate_limits.items():
                    while timestamps and timestamps[0] <= cutoff:
                        timestamps.popleft()
                    if not timestamps:
                        empty_rate_limits.append(id_)
                for id_ in empty_rate_limits:
                    del self._rate_limits[id_]

            self._stop_event.wait(600)  # Sleep for 10 minutes

# Singleton instance for app-wide use
immune_system = ImmuneSystem()

# --- Utility functions ---

def get_immune_status() -> dict:
    """Return basic health status of ImmuneSystem."""
    if immune_system._initialized:
        return {"active": True, "healthy": True, "info": "Immune System operational"}
    else:
        return {"active": False, "healthy": False, "info": "Immune System not initialized"}

def get_immune_transaction_state(txn_id: str) -> dict:
    """Placeholder stub to check immune status of a transaction."""
    # You can expand this function based on actual transaction tracking
    return {"state": "clear", "confirmed": True}
