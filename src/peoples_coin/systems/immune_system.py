# src/peoples_coin/systems/immune_system.py

import os
import time
import threading
import logging
import http
from functools import wraps
from collections import defaultdict
from typing import Optional, Callable, Dict, Any

from flask import request, jsonify, Flask, g, Blueprint

# Use our secure decorator for the management endpoints
from peoples_coin.utils.auth import require_api_key

try:
    from redis import Redis, exceptions as RedisExceptions
except ImportError:
    Redis = None
    RedisExceptions = None

logger = logging.getLogger(__name__)

#
# The ImmuneSystem class is already excellent and requires no changes.
# All the code from your original file for the class goes here.
# ... (The entire ImmuneSystem class from your submission)
#

class ImmuneSystem:
    """
    Immune System: A resilient security layer for Flask apps.
    - Features rate limiting, greylisting, and blacklisting.
    - Uses a non-blocking startup sequence and lazy Redis connections.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self._redis_client: Optional[Redis] = None
        self._redis_lock = threading.Lock()
        
        # In-memory fallbacks
        self._in_memory_lock = threading.Lock()
        self._blacklist = set()
        self._greylist = defaultdict(lambda: {"count": 0, "last_seen": 0})
        self._rate_limits = defaultdict(list)

        # Cleaner thread control
        self._stop_event = threading.Event()
        self._cleaner_thread: Optional[threading.Thread] = None
        self._initialized = False
        logger.info("🫀 ImmuneSystem instance created.")

    def init_app(self, app: Flask):
        """
        Configures the Immune System. This method is fast and non-blocking.
        It only stores configuration and does not make any network calls.
        """
        if self._initialized:
            return

        self.app = app
        self.config = app.config

        # Set default configurations
        self.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        self.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        self.config.setdefault("REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        
        self._initialized = True
        logger.info("🛡️ ImmuneSystem configured.")

    @property
    def connection(self) -> Optional[Redis]:
        """
        Provides a lazy-loading, thread-safe Redis connection.
        The connection is only attempted when this property is first accessed.
        """
        if Redis is None:
            return None
            
        # Check if we have a valid, active connection
        if self._redis_client:
            try:
                if self._redis_client.ping():
                    return self._redis_client
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis connection lost. Attempting to reconnect.")
                self._redis_client = None

        # If no active connection, try to establish one
        with self._redis_lock:
            # Double-check inside the lock in case another thread just connected
            if self._redis_client:
                return self._redis_client

            logger.info("🛡️ Attempting to connect to Redis...")
            try:
                redis_client = Redis.from_url(
                    self.config["REDIS_URL"], decode_responses=True,
                    socket_connect_timeout=1
                )
                redis_client.ping()
                self._redis_client = redis_client
                logger.info("✅ ImmuneSystem connected to Redis.")
                return self._redis_client
            except (RedisExceptions.RedisError, ValueError) as e:
                logger.error(f"🛡️ Could not connect to Redis: {e}. Falling back to in-memory store.")
                self._redis_client = None
                return None

    def start(self):
        """Starts the background cleaner thread. Safe to call multiple times."""
        if not self._initialized:
            logger.error("🚫 Cannot start cleaner: ImmuneSystem not initialized.")
            return

        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            logger.info("▶️ Starting ImmuneSystem cleaner thread...")
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(
                target=self._cleaner_task, daemon=True, name="ImmuneCleaner"
            )
            self._cleaner_thread.start()

    def stop(self):
        """Stops the cleaner thread gracefully."""
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            logger.info("🛑 Stopping ImmuneSystem cleaner thread...")
            self._stop_event.set()
            self._cleaner_thread.join(timeout=5)
            logger.info("✅ ImmuneSystem cleaner thread stopped.")

    def _get_identifier(self) -> str:
        """Returns a unique identifier for the client (IP, API Key, or User ID)."""
        # In our refined auth decorators, g.user will be the UserAccount object
        if hasattr(g, "user") and g.user:
            return f"user:{g.user.id}"
        # For API key auth, g.user is also set
        if (api_key := request.headers.get("X-API-Key")):
            return f"api_key:{api_key}"
        return f"ip:{request.remote_addr or 'unknown'}"

    def is_blacklisted(self, identifier: str) -> bool:
        """Checks if an identifier is on the blacklist."""
        redis = self.connection
        if redis:
            try:
                return redis.sismember("immune:blacklist", identifier)
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error in is_blacklisted: {e}. Falling back to memory.")

        with self._in_memory_lock:
            return identifier in self._blacklist

    def add_to_blacklist(self, identifier: str):
        """Adds an identifier to the blacklist."""
        redis = self.connection
        if redis:
            try:
                redis.sadd("immune:blacklist", identifier)
                logger.warning(f"🛡️ Blacklisted {identifier} (Redis).")
                return
            except RedisExceptions.RedisError as e:
                logger.warning(f"🛡️ Redis error adding to blacklist: {e}.")

        with self._in_memory_lock:
            self._blacklist.add(identifier)
            logger.warning(f"🛡️ Blacklisted {identifier} (memory).")

    def record_invalid_attempt(self, identifier: str):
        """Tracks a failed attempt, blacklisting if a threshold is exceeded."""
        if self.is_blacklisted(identifier):
            return

        max_attempts = self.config["IMMUNE_MAX_INVALID_ATTEMPTS"]
        quarantine = self.config["IMMUNE_QUARANTINE_TIME_SEC"]
        
        redis = self.connection
        if redis:
            try:
                key = f"immune:greylist:{identifier}"
                count = redis.incr(key)
                redis.expire(key, quarantine)
                if count >= max_attempts:
                    self.add_to_blacklist(identifier)
                    redis.delete(key)
                return
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis error in record_invalid_attempt. Falling back.")

        with self._in_memory_lock:
            entry = self._greylist[identifier]
            entry["count"] += 1
            entry["last_seen"] = time.time()
            if entry["count"] >= max_attempts:
                self.add_to_blacklist(identifier)
                del self._greylist[identifier]

    def _is_rate_limited(self, identifier: str) -> bool:
        """Checks if a client has exceeded their request rate limit."""
        max_reqs = self.config.get("IMMUNE_MAX_REQUESTS_PER_WINDOW", 30)
        window = self.config.get("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        
        redis = self.connection
        if redis:
            try:
                key = f"immune:rate_limit:{identifier}"
                p = redis.pipeline()
                p.incr(key)
                p.expire(key, window, nx=True) # Set expiry only if key is new
                count, _ = p.execute()
                return count > max_reqs
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis error in rate limit check. Falling back.")
        
        now = time.time()
        with self._in_memory_lock:
            timestamps = self._rate_limits[identifier]
            # Filter out old timestamps
            timestamps = [ts for ts in timestamps if ts > now - window]
            timestamps.append(now)
            self._rate_limits[identifier] = timestamps
            return len(timestamps) > max_reqs


    def check(self) -> Callable:
        """A Flask route decorator that applies all immune system checks."""
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def wrapper(*args, **kwargs):
                identifier = self._get_identifier()
                if self.is_blacklisted(identifier):
                    return jsonify({"error": "Access denied"}), http.HTTPStatus.FORBIDDEN
                if self._is_rate_limited(identifier):
                    return jsonify({"error": "Too many requests"}), http.HTTPStatus.TOO_MANY_REQUESTS
                return f(*args, **kwargs)
            return wrapper
        return decorator

    def _cleaner_task(self):
        """A background task to periodically clean up in-memory fallback stores."""
        logger.info("🛡️ ImmuneSystem cleaner thread started.")
        while not self._stop_event.is_set():
            try:
                now = time.time()
                quarantine = self.config["IMMUNE_QUARANTINE_TIME_SEC"]
                
                with self._in_memory_lock:
                    expired_keys = [k for k, v in self._greylist.items() if now - v["last_seen"] > quarantine]
                    for k in expired_keys:
                        del self._greylist[k]
                    if expired_keys:
                        logger.info(f"🛡️ Cleaned {len(expired_keys)} expired greylist entries.")
            
            except Exception as e:
                logger.error(f"🛡️ Cleaner thread error: {e}", exc_info=True)
            
            # Wait for 10 minutes before the next cleanup
            self._stop_event.wait(600)
        logger.info("🛡️ ImmuneSystem cleaner thread stopped.")


# --- Singleton Instance ---
immune_system = ImmuneSystem()

# ========== Flask Blueprint for Immune System Endpoints ==========

immune_bp = Blueprint("immune", __name__, url_prefix="/immune")


@immune_bp.route("/status", methods=["GET"])
@require_api_key # Secure this endpoint
def immune_status():
    """Returns basic status of the immune system."""
    redis_conn = immune_system.connection
    # For security, avoid leaking too much internal state in a public status check
    status = {
        "redis_connected": redis_conn is not None,
    }
    return jsonify(status), http.HTTPStatus.OK


@immune_bp.route("/blacklist", methods=["POST"])
@require_api_key # Secure this endpoint
def add_blacklist():
    """
    Adds an identifier (IP, API key, user ID) to the blacklist.
    Requires a valid API key with administrative privileges.
    Request JSON: {"identifier": "string"}
    """
    data = request.get_json(silent=True)
    if not data or "identifier" not in data:
        return jsonify({"error": "Missing 'identifier' in request body"}), http.HTTPStatus.BAD_REQUEST

    identifier = data["identifier"]
    immune_system.add_to_blacklist(identifier)
    return jsonify({"status": "success", "blacklisted": identifier}), http.HTTPStatus.CREATED


@immune_bp.route("/blacklist", methods=["GET"])
@require_api_key # Secure this endpoint
def get_blacklist():
    """
S    Returns the list of currently blacklisted identifiers from Redis.
    Requires a valid API key.
    """
    redis = immune_system.connection
    blacklist = []
    if redis:
        try:
            blacklist = list(redis.smembers("immune:blacklist"))
        except RedisExceptions.RedisError as e:
            logger.error(f"Could not retrieve blacklist from Redis: {e}")
            return jsonify({"error": "Failed to retrieve blacklist from Redis"}), http.HTTPStatus.INTERNAL_SERVER_ERROR
    else:
        # Fallback to in-memory if Redis is down
        with immune_system._in_memory_lock:
            blacklist = list(immune_system._blacklist)

    return jsonify({"blacklist": blacklist}), http.HTTPStatus.OK
