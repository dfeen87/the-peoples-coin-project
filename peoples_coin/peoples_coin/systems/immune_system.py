import os
import time
import threading
import logging
from functools import wraps
from collections import defaultdict
from flask import request, jsonify, current_app # Import current_app
from redis import Redis, RedisError
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ====== CONFIGURATION ======
QUARANTINE_TIME_SEC = int(os.getenv("QUARANTINE_TIME_SEC", 300))  # 5 minutes
MAX_INVALID_ATTEMPTS = int(os.getenv("MAX_INVALID_ATTEMPTS", 5))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", 60))
MAX_REQUESTS_PER_WINDOW = int(os.getenv("MAX_REQUESTS_PER_WINDOW", 30))
BLACKLIST_EXPIRY_SEC = int(os.getenv("BLACKLIST_EXPELIST_EXPIRY_SEC", 3600))  # 1 hour blacklist expiration (optional)

# ====== REDIS SETUP (Lazy Initialization) ======
_redis: Optional[Redis] = None
_redis_enabled: bool = False
_redis_lock = threading.Lock() # To ensure thread-safe lazy init

def _get_redis_client() -> Optional[Redis]:
    """Lazily initializes and returns the Redis client."""
    global _redis, _redis_enabled
    if _redis is None:
        with _redis_lock:
            if _redis is None: # Double-checked locking
                try:
                    _redis = Redis(
                        host=os.getenv("REDIS_HOST", "localhost"),
                        port=int(os.getenv("REDIS_PORT", 6379)),
                        db=int(os.getenv("REDIS_DB", 0)),
                        decode_responses=True,
                        socket_connect_timeout=2,
                    )
                    _redis.ping() # Test connection
                    _redis_enabled = True
                    logger.info("ImmuneSystem: Using Redis backend for persistence.")
                except (RedisError, Exception) as e:
                    _redis = None # Ensure it's None if connection fails
                    _redis_enabled = False
                    logger.warning(f"ImmuneSystem: Redis unavailable, falling back to in-memory store. Error: {e}")
    return _redis

def is_redis_enabled() -> bool:
    # Attempt to get client to ensure _redis_enabled is set
    _get_redis_client() 
    return _redis_enabled

# ====== IN-MEMORY FALLBACK ======
_lock = threading.Lock()
_blacklist = set()
_greylist = defaultdict(lambda: {"count": 0, "last_seen": 0, "first_seen": time.time()})
_rate_limits = defaultdict(list)

# ====== BACKGROUND CLEANER THREAD MANAGEMENT ======
_stop_event = threading.Event()
_cleaner_thread = None

def _clean_greylist():
    while not _stop_event.is_set():
        try:
            now = time.time()
            with _lock:
                to_remove = [
                    k for k, v in _greylist.items()
                    if now - v["last_seen"] > QUARANTINE_TIME_SEC
                ]
                for k in to_remove:
                    del _greylist[k]
            _stop_event.wait(600)  # sleep 10 minutes but wake early if stop_event set
        except Exception as e:
            logger.error(f"ImmuneSystem: Greylist cleaner error: {e}")

def start_immune_system_cleaner():
    global _cleaner_thread
    if _cleaner_thread is None or not _cleaner_thread.is_alive():
        _stop_event.clear()
        _cleaner_thread = threading.Thread(target=_clean_greylist, daemon=True, name="ImmuneSystemCleaner")
        _cleaner_thread.start()
        logger.info("ImmuneSystem: Cleaner thread started.")

def stop_immune_system_cleaner():
    _stop_event.set()
    if _cleaner_thread and _cleaner_thread.is_alive():
        _cleaner_thread.join(timeout=5) # Add timeout for graceful shutdown
        if _cleaner_thread.is_alive():
            logger.warning("ImmuneSystem: Cleaner thread did not stop gracefully.")
        logger.info("ImmuneSystem: Cleaner thread stopped.")

# ====== HELPER FUNCTIONS ======
def _get_identifier() -> str:
    """
    Extract an identifier for the client/requestor.
    Prioritizes X-User-Id header, falls back to remote IP, else 'unknown'.
    Requires Flask request context.
    """
    # This function should only be called within a Flask request context.
    # If called outside, request will be None.
    if request:
        user_id = request.headers.get("X-User-Id")
        if user_id:
            return user_id
        return request.remote_addr or "unknown"
    else:
        # Fallback for CLI or background tasks that need an identifier but not tied to a request
        # You might want a more specific fallback here depending on context
        return "cli_or_background_task"

def is_blacklisted(identifier: str) -> bool:
    _redis_client = _get_redis_client()
    if _redis_client and is_redis_enabled():
        try:
            return _redis_client.sismember("blacklist", identifier)
        except RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on is_blacklisted: {e}")
            # fallback to in-memory on Redis failure
    with _lock:
        return identifier in _blacklist

def add_to_blacklist(identifier: str) -> None:
    _redis_client = _get_redis_client()
    if _redis_client and is_redis_enabled():
        try:
            _redis_client.sadd("blacklist", identifier)
            if BLACKLIST_EXPIRY_SEC > 0:
                _redis_client.expire("blacklist", BLACKLIST_EXPIRY_SEC)
        except RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on add_to_blacklist: {e}")
            with _lock:
                _blacklist.add(identifier)
    else:
        with _lock:
            _blacklist.add(identifier)
    logger.info(f"ImmuneSystem: {identifier} added to blacklist.")

def record_invalid_attempt(identifier: str) -> None:
    _redis_client = _get_redis_client()
    if _redis_client and is_redis_enabled():
        try:
            key = f"greylist:{identifier}"
            _redis_client.hincrby(key, "count", 1)
            _redis_client.hset(key, "last_seen", time.time())
            if not _redis_client.hexists(key, "first_seen"):
                _redis_client.hset(key, "first_seen", time.time())
            count = int(_redis_client.hget(key, "count"))
        except RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on record_invalid_attempt: {e}")
            with _lock:
                gl = _greylist[identifier]
                gl["count"] += 1
                gl["last_seen"] = time.time()
                count = gl["count"]
    else:
        with _lock:
            gl = _greylist[identifier]
            gl["count"] += 1
            gl["last_seen"] = time.time()
            count = gl["count"]

    if count >= MAX_INVALID_ATTEMPTS:
        add_to_blacklist(identifier)

def check_rate_limit(identifier: str) -> bool:
    now = time.time()
    _redis_client = _get_redis_client()
    if _redis_client and is_redis_enabled():
        try:
            key = f"ratelimit:{identifier}"
            _redis_client.zadd(key, {str(now): now})
            _redis_client.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW_SEC)
            count = _redis_client.zcard(key)
            if count > MAX_REQUESTS_PER_WINDOW:
                return False
            _redis_client.expire(key, RATE_LIMIT_WINDOW_SEC)
        except RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on check_rate_limit: {e}")
            # fallback to in-memory
            with _lock: # Ensure fallback uses in-memory store even if Redis fails mid-operation
                window = _rate_limits[identifier]
                window = [t for t in window if now - t < RATE_LIMIT_WINDOW_SEC]
                window.append(now)
                _rate_limits[identifier] = window
                if len(window) > MAX_REQUESTS_PER_WINDOW:
                    return False
    else: # Always use in-memory if Redis not enabled or failed initially
        with _lock:
            window = _rate_limits[identifier]
            window = [t for t in window if now - t < RATE_LIMIT_WINDOW_SEC]
            window.append(now)
            _rate_limits[identifier] = window
            if len(window) > MAX_REQUESTS_PER_WINDOW:
                return False
    return True

def reset_immune_system() -> None:
    _redis_client = _get_redis_client()
    if _redis_client and is_redis_enabled():
        try:
            _redis_client.delete("blacklist")
            for key in _redis_client.scan_iter("greylist:*"):
                _redis_client.delete(key)
            for key in _redis_client.scan_iter("ratelimit:*"):
                _redis_client.delete(key)
        except RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on reset: {e}")
            with _lock:
                _blacklist.clear()
                _greylist.clear()
                _rate_limits.clear()
    else:
        with _lock:
            _blacklist.clear()
            _greylist.clear()
            _rate_limits.clear()
    logger.info("ImmuneSystem: All state reset.")

def get_blacklist() -> List[str]:
    _redis_client = _get_redis_client()
    if _redis_client and is_redis_enabled():
        try:
            return list(_redis_client.smembers("blacklist"))
        except RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on get_blacklist: {e}")
            with _lock:
                return list(_blacklist)
    with _lock:
        return list(_blacklist)

# ====== AUTO-HEAL PLACEHOLDER ======
def auto_heal_entries(data_entries: List[Dict]) -> int:
    """
    Attempt to heal/correct invalid data entries.
    Currently a placeholder — implement domain-specific healing logic here.
    """
    logger.info(f"ImmuneSystem: Auto-healing invoked on {len(data_entries)} entries")
    # TODO: Implement healing logic here
    return 0

# ====== DECORATOR ======
def immune_check(f):
    """
    Decorator to apply immune system checks before allowing request.
    Checks blacklist and rate limits.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Ensure _get_identifier() and other functions get the correct identifier
        # This will now implicitly trigger _get_redis_client() on first use
        identifier = _get_identifier()
        if is_blacklisted(identifier):
            logger.warning(f"ImmuneSystem: Blocked blacklisted identifier: {identifier}")
            return jsonify({"error": "You are blacklisted"}), 403

        if not check_rate_limit(identifier):
            logger.warning(f"ImmuneSystem: Rate limit exceeded for {identifier}")
            return jsonify({"error": "Rate limit exceeded"}), 429

        return f(*args, **kwargs)

    return decorated

# Define a function to register the shutdown hook for the cleaner thread
def register_immune_system_shutdown(app):
    """Registers the cleaner thread shutdown with the Flask app context."""
    @app.teardown_appcontext
    def teardown(exception=None):
        stop_immune_system_cleaner()
    
    # Also ensure the cleaner starts when the app starts
    # This can be done in your create_app function or directly here if appropriate
    with app.app_context(): # Ensure app context is pushed to run this immediately
        start_immune_system_cleaner()
