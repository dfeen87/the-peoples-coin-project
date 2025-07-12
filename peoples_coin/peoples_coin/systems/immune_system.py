# peoples_coin/peoples_coin/systems/immune_system.py

import os
import time
import threading
import logging
from functools import wraps
from collections import defaultdict
from flask import request, jsonify
from redis import Redis, exceptions
from typing import Optional, List

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
QUARANTINE_TIME_SEC = int(os.getenv("QUARANTINE_TIME_SEC", 300))
MAX_INVALID_ATTEMPTS = int(os.getenv("MAX_INVALID_ATTEMPTS", 5))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", 60))
MAX_REQUESTS_PER_WINDOW = int(os.getenv("MAX_REQUESTS_PER_WINDOW", 30))

# --- STATE ---
_redis: Optional[Redis] = None
_redis_lock = threading.Lock()

_in_memory_lock = threading.Lock()
_blacklist = set()
_greylist = defaultdict(lambda: {"count": 0, "last_seen": 0})
_rate_limits = defaultdict(list)

_stop_event = threading.Event()
_cleaner_thread: Optional[threading.Thread] = None


# --- REDIS HANDLING ---
def get_redis_client() -> Optional[Redis]:
    """
    Lazily initializes and returns the Redis client, thread-safe.
    Falls back to in-memory if Redis is unavailable.
    """
    global _redis
    if _redis is None:
        with _redis_lock:
            if _redis is None:
                logger.info("🛡️ ImmuneSystem: Connecting to Redis...")
                try:
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
                    _redis = Redis.from_url(
                        redis_url,
                        decode_responses=True,
                        socket_connect_timeout=1,
                        socket_timeout=1
                    )
                    _redis.ping()
                    logger.info("🛡️ ImmuneSystem: Connected to Redis.")
                except (exceptions.ConnectionError, exceptions.TimeoutError, ValueError) as e:
                    logger.warning(f"🛡️ ImmuneSystem: Redis unavailable, falling back to memory. Error: {e}")
                    _redis = None
    return _redis


def is_redis_enabled() -> bool:
    """Checks if Redis is available and functional."""
    return get_redis_client() is not None


# --- BACKGROUND CLEANER ---
def _clean_in_memory_stores():
    """
    Periodically cleans up in-memory quarantine & rate-limiting data if Redis is not used.
    """
    logger.info("🛡️ ImmuneSystem cleaner thread running.")
    while not _stop_event.is_set():
        try:
            if not is_redis_enabled():
                now = time.time()
                with _in_memory_lock:
                    to_remove = [k for k, v in _greylist.items() if now - v["last_seen"] > QUARANTINE_TIME_SEC]
                    for k in to_remove:
                        del _greylist[k]
            _stop_event.wait(600)  # Every 10 minutes
        except Exception as e:
            logger.error(f"🛡️ ImmuneSystem cleaner error: {e}", exc_info=True)
    logger.info("🛡️ ImmuneSystem cleaner thread exiting.")


def start_immune_system_cleaner():
    """Starts the background cleaner thread."""
    global _cleaner_thread
    if not _cleaner_thread or not _cleaner_thread.is_alive():
        _stop_event.clear()
        _cleaner_thread = threading.Thread(
            target=_clean_in_memory_stores,
            daemon=True,
            name="ImmuneSystemCleaner"
        )
        _cleaner_thread.start()
        logger.info("🛡️ ImmuneSystem cleaner thread started.")


def stop_immune_system_cleaner():
    """Stops the background cleaner thread."""
    _stop_event.set()
    if _cleaner_thread and _cleaner_thread.is_alive():
        _cleaner_thread.join(timeout=5)
    logger.info("🛡️ ImmuneSystem cleaner thread stopped.")


# --- HELPER FUNCTIONS ---
def get_identifier() -> str:
    """
    Determines a unique identifier for the requestor: X-User-Id header or IP.
    """
    if not request:
        return "cli_or_background_task"
    return request.headers.get("X-User-Id") or request.remote_addr or "unknown"


def is_blacklisted(identifier: str) -> bool:
    """
    Checks if the identifier is blacklisted.
    """
    r = get_redis_client()
    if r:
        try:
            return r.sismember("blacklist", identifier)
        except exceptions.RedisError as e:
            logger.warning(f"🛡️ Redis error during is_blacklisted: {e}")
    with _in_memory_lock:
        return identifier in _blacklist


# --- SECURITY DECORATORS ---
def immune_check(func):
    """
    Decorator to apply immune checks (rate limiting & blacklisting) to routes.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        identifier = get_identifier()

        if is_blacklisted(identifier):
            logger.warning(f"🛡️ Blocked blacklisted identifier: {identifier}")
            return jsonify({"error": "Access denied"}), 403

        now = time.time()
        with _in_memory_lock:
            requests_list = _rate_limits[identifier]
            requests_list = [ts for ts in requests_list if now - ts <= RATE_LIMIT_WINDOW_SEC]
            requests_list.append(now)
            _rate_limits[identifier] = requests_list

            if len(requests_list) > MAX_REQUESTS_PER_WINDOW:
                logger.warning(f"🛡️ Rate limit exceeded by {identifier}")
                return jsonify({"error": "Too many requests"}), 429

        return func(*args, **kwargs)

    return wrapper

