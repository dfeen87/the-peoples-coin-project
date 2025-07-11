# peoples_coin/peoples_coin/systems/immune_system.py

import os
import time
import threading
import logging
from functools import wraps
from collections import defaultdict
from flask import request, jsonify
from redis import Redis, exceptions
from typing import List, Optional

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
QUARANTINE_TIME_SEC = int(os.getenv("QUARANTINE_TIME_SEC", 300))
MAX_INVALID_ATTEMPTS = int(os.getenv("MAX_INVALID_ATTEMPTS", 5))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", 60))
MAX_REQUESTS_PER_WINDOW = int(os.getenv("MAX_REQUESTS_PER_WINDOW", 30))

# --- STATE & LAZY INITIALIZATION ---
_redis: Optional[Redis] = None
_redis_lock = threading.Lock()

_in_memory_lock = threading.Lock()
_blacklist = set()
_greylist = defaultdict(lambda: {"count": 0, "last_seen": 0})
_rate_limits = defaultdict(list)

def get_redis_client() -> Optional[Redis]:
    """Lazily initializes and returns the Redis client in a thread-safe way."""
    global _redis
    if _redis is None:
        with _redis_lock:
            if _redis is None:
                logger.info("🛡️ ImmuneSystem: Attempting to connect to Redis...")
                try:
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
                    _redis = Redis.from_url(
                        redis_url,
                        decode_responses=True,
                        socket_connect_timeout=1,
                        socket_timeout=1
                    )
                    _redis.ping()
                    logger.info("🛡️ ImmuneSystem: Successfully connected to Redis backend.")
                except (exceptions.ConnectionError, exceptions.TimeoutError, ValueError) as e:
                    _redis = None
                    logger.warning(f"🛡️ ImmuneSystem: Redis unavailable, falling back to in-memory store. Error: {e}")
    return _redis

def is_redis_enabled() -> bool:
    """Checks if Redis is available and connected."""
    return get_redis_client() is not None

# --- BACKGROUND CLEANER ---
_stop_event = threading.Event()
_cleaner_thread = None

def _clean_in_memory_stores():
    """Cleans up in-memory data if Redis is not used."""
    while not _stop_event.is_set():
        try:
            if not is_redis_enabled():
                now = time.time()
                with _in_memory_lock:
                    to_remove = [k for k, v in _greylist.items() if now - v["last_seen"] > QUARANTINE_TIME_SEC]
                    for k in to_remove:
                        del _greylist[k]
            _stop_event.wait(600)
        except Exception as e:
            logger.error(f"ImmuneSystem cleaner error: {e}")

def start_immune_system_cleaner():
    """Starts the background cleaner thread."""
    global _cleaner_thread
    if _cleaner_thread is None or not _cleaner_thread.is_alive():
        _stop_event.clear()
        _cleaner_thread = threading.Thread(target=_clean_in_memory_stores, daemon=True, name="ImmuneSystemCleaner")
        _cleaner_thread.start()
        logger.info("🛡️ Immune System cleaner thread started.")

def stop_immune_system_cleaner():
    """Stops the background cleaner thread."""
    _stop_event.set()
    if _cleaner_thread and _cleaner_thread.is_alive():
        _cleaner_thread.join(timeout=5)
    logger.info("🛡️ Immune System cleaner thread stopped.")

# --- HELPER FUNCTIONS ---
def get_identifier() -> str:
    """Gets a unique identifier for the current request."""
    if not request:
        return "cli_or_background_task"
    return request.headers.get("X-User-Id") or request.remote_addr or "unknown"

def is_blacklisted(identifier: str) -> bool:
    """Checks if an identifier is blacklisted."""
    r = get_redis_client()
    if r:
        try:
            return r.sismember("blacklist", identifier)
        except exceptions.RedisError as e:
            logger.warning(f"ImmuneSystem: Redis error on is_blacklisted: {e}")
    with _in_memory_lock:
        return identifier in _blacklist
