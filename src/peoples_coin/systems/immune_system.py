# src/peoples_coin/systems/immune_system.py

import os
import time
import threading
import logging
import http
import hashlib
import random
from functools import wraps
from collections import defaultdict
from typing import Optional, Callable, Dict, Any

from flask import request, jsonify, Flask, g, Blueprint

# Secure decorator for management endpoints
from peoples_coin.utils.auth import require_api_key

try:
    from redis import Redis, exceptions as RedisExceptions
except ImportError:
    Redis = None
    RedisExceptions = None

logger = logging.getLogger(__name__)

class ImmuneSystem:
    """
    Hardened Immune System for Flask apps.
    - Rate limiting, greylisting, blacklisting, proof-of-work (PoW), honeypot detection.
    - Adaptive thresholds for low/high trust clients.
    - Caches PoW solves by IP to reduce friction for legit users.
    - Redis + in-memory fallback.
    """

    def __init__(self):
        self.app: Optional[Flask] = None
        self.config: Dict[str, Any] = {}
        self._redis_client: Optional[Redis] = None
        self._redis_lock = threading.Lock()
        
        # In-memory fallback structures
        self._in_memory_lock = threading.Lock()
        self._blacklist = {}  # identifier -> expiry_time
        self._greylist = defaultdict(lambda: {"count": 0, "last_seen": 0})
        self._rate_limits = defaultdict(list)
        self._pow_cache = {}  # ip -> expiry_time

        # Cleaner thread control
        self._stop_event = threading.Event()
        self._cleaner_thread: Optional[threading.Thread] = None
        self._initialized = False
        logger.info("🫀 Hardened ImmuneSystem instance created.")

    def init_app(self, app: Flask):
        if self._initialized:
            return

        self.app = app
        self.config = app.config

        # Default configurations
        self.config.setdefault("IMMUNE_QUARANTINE_TIME_SEC", 300)
        self.config.setdefault("IMMUNE_MAX_INVALID_ATTEMPTS", 5)
        self.config.setdefault("REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        self.config.setdefault("IMMUNE_MAX_REQUESTS_LOW_TRUST", 20)
        self.config.setdefault("IMMUNE_MAX_REQUESTS_HIGH_TRUST", 60)
        self.config.setdefault("IMMUNE_RATE_LIMIT_WINDOW_SEC", 60)
        self.config.setdefault("IMMUNE_BLACKLIST_DECAY_SEC", 3600)  # 1 hour
        self.config.setdefault("IMMUNE_ENABLE_POW", True)
        self.config.setdefault("IMMUNE_POW_DIFFICULTY", 4)  # number of leading zeros in hash
        self.config.setdefault("IMMUNE_ENABLE_HONEYPOT", True)
        self.config.setdefault("IMMUNE_POW_TTL_SEC", 600)  # PoW cache duration per IP (10 min)

        self._initialized = True
        logger.info("🛡️ Hardened ImmuneSystem configured.")

    @property
    def connection(self) -> Optional[Redis]:
        """Lazy, thread-safe Redis connection."""
        if Redis is None:
            return None

        if self._redis_client:
            try:
                if self._redis_client.ping():
                    return self._redis_client
            except RedisExceptions.RedisError:
                logger.warning("🛡️ Redis connection lost. Reconnecting.")
                self._redis_client = None

        with self._redis_lock:
            if self._redis_client:
                return self._redis_client
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
                logger.error(f"🛡️ Redis connect failed: {e}. Using in-memory store.")
                return None

    def start(self):
        if not self._initialized:
            logger.error("🚫 Cannot start: ImmuneSystem not initialized.")
            return

        if not self._cleaner_thread or not self._cleaner_thread.is_alive():
            logger.info("▶️ Starting Hardened ImmuneSystem cleaner thread...")
            self._stop_event.clear()
            self._cleaner_thread = threading.Thread(
                target=self._cleaner_task, daemon=True, name="ImmuneCleaner"
            )
            self._cleaner_thread.start()

    def stop(self):
        if self._cleaner_thread and self._cleaner_thread.is_alive():
            logger.info("🛑 Stopping ImmuneSystem cleaner thread...")
            self._stop_event.set()
            self._cleaner_thread.join(timeout=5)
            logger.info("✅ Cleaner stopped.")

    def _get_identifier(self) -> str:
        if hasattr(g, "user") and g.user:
            return f"user:{g.user.id}"
        if (api_key := request.headers.get("X-API-Key")):
            return f"api_key:{api_key}"
        return f"ip:{request.remote_addr or 'unknown'}"

    # ---------- Blacklist Handling ----------

    def is_blacklisted(self, identifier: str) -> bool:
        now = time.time()
        with self._in_memory_lock:
            expiry = self._blacklist.get(identifier)
            if expiry and expiry > now:
                return True
            elif expiry:
                del self._blacklist[identifier]
        return False

    def add_to_blacklist(self, identifier: str, duration=None):
        duration = duration or self.config["IMMUNE_BLACKLIST_DECAY_SEC"]
        expiry = time.time() + duration
        with self._in_memory_lock:
            self._blacklist[identifier] = expiry
        logger.warning(f"🛡️ Blacklisted {identifier} for {duration} sec.")

    # ---------- Invalid Attempt Tracking ----------

    def record_invalid_attempt(self, identifier: str):
        if self.is_blacklisted(identifier):
            return
        entry = self._greylist[identifier]
        entry["count"] += 1
        entry["last_seen"] = time.time()
        if entry["count"] >= self.config["IMMUNE_MAX_INVALID_ATTEMPTS"]:
            self.add_to_blacklist(identifier)
            del self._greylist[identifier]

    # ---------- Adaptive Rate Limiting ----------

    def _is_rate_limited(self, identifier: str) -> bool:
        high_trust = identifier.startswith("user:") or identifier.startswith("api_key:")
        max_reqs = self.config["IMMUNE_MAX_REQUESTS_HIGH_TRUST"] if high_trust else self.config["IMMUNE_MAX_REQUESTS_LOW_TRUST"]
        window = self.config["IMMUNE_RATE_LIMIT_WINDOW_SEC"]

        now = time.time()
        with self._in_memory_lock:
            timestamps = [ts for ts in self._rate_limits[identifier] if ts > now - window]
            timestamps.append(now)
            self._rate_limits[identifier] = timestamps
            return len(timestamps) > max_reqs

    # ---------- Proof-of-Work Challenge ----------

    def _pow_solved_recently(self, ip: str) -> bool:
        now = time.time()
        redis = self.connection
        ttl = self.config["IMMUNE_POW_TTL_SEC"]

        if redis:
            try:
                return redis.exists(f"immune:pow_solved:{ip}") == 1
            except RedisExceptions.RedisError:
                pass

        with self._in_memory_lock:
            expiry = self._pow_cache.get(ip)
            if expiry and expiry > now:
                return True
            elif expiry:
                del self._pow_cache[ip]
        return False

    def _mark_pow_solved(self, ip: str):
        expiry = time.time() + self.config["IMMUNE_POW_TTL_SEC"]
        redis = self.connection
        if redis:
            try:
                redis.setex(f"immune:pow_solved:{ip}", self.config["IMMUNE_POW_TTL_SEC"], "1")
                return
            except RedisExceptions.RedisError:
                pass
        with self._in_memory_lock:
            self._pow_cache[ip] = expiry

    def _verify_pow(self):
        if not self.config["IMMUNE_ENABLE_POW"]:
            return True
        difficulty = self.config["IMMUNE_POW_DIFFICULTY"]
        nonce = request.headers.get("X-PoW-Nonce")
        challenge = request.headers.get("X-PoW-Challenge")
        if not nonce or not challenge:
            return False
        guess = f"{challenge}{nonce}".encode()
        digest = hashlib.sha256(guess).hexdigest()
        return digest.startswith("0" * difficulty)

    def generate_pow_challenge(self):
        return hashlib.sha256(str(random.random()).encode()).hexdigest()

    # ---------- Honeypot Trap ----------

    def _honeypot_triggered(self):
        if not self.config["IMMUNE_ENABLE_HONEYPOT"]:
            return False
        if request.form.get("extra_field") or request.args.get("extra_field"):
            return True
        return False

    # ---------- Main Security Check Decorator ----------

    def check(self) -> Callable:
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def wrapper(*args, **kwargs):
                identifier = self._get_identifier()

                # Honeypot check
                if self._honeypot_triggered():
                    self.add_to_blacklist(identifier)
                    return jsonify({"error": "Access denied"}), http.HTTPStatus.FORBIDDEN

                # Blacklist check
                if self.is_blacklisted(identifier):
                    return jsonify({"error": "Access denied"}), http.HTTPStatus.FORBIDDEN

                # Rate limit check
                if self._is_rate_limited(identifier):
                    return jsonify({"error": "Too many requests"}), http.HTTPStatus.TOO_MANY_REQUESTS

                # PoW check for low-trust clients
                if not identifier.startswith("user:") and not identifier.startswith("api_key:"):
                    ip = identifier.replace("ip:", "")
                    if not self._pow_solved_recently(ip):
                        if not self._verify_pow():
                            challenge = self.generate_pow_challenge()
                            return jsonify({
                                "error": "PoW required",
                                "challenge": challenge,
                                "difficulty": self.config["IMMUNE_POW_DIFFICULTY"]
                            }), http.HTTPStatus.FORBIDDEN
                        else:
                            self._mark_pow_solved(ip)

                return f(*args, **kwargs)
            return wrapper
        return decorator

    # ---------- Cleaner Thread ----------

    def _cleaner_task(self):
        logger.info("🛡️ Hardened ImmuneSystem cleaner thread started.")
        while not self._stop_event.is_set():
            try:
                now = time.time()
                quarantine = self.config["IMMUNE_QUARANTINE_TIME_SEC"]

                with self._in_memory_lock:
                    # Greylist cleanup
                    expired_keys = [k for k, v in self._greylist.items() if now - v["last_seen"] > quarantine]
                    for k in expired_keys:
                        del self._greylist[k]

                    # Blacklist cleanup
                    expired_blacklist = [k for k, exp in self._blacklist.items() if exp <= now]
                    for k in expired_blacklist:
                        del self._blacklist[k]

                    # PoW cache cleanup
                    expired_pow = [ip for ip, exp in self._pow_cache.items() if exp <= now]
                    for ip in expired_pow:
                        del self._pow_cache[ip]

            except Exception as e:
                logger.error(f"🛡️ Cleaner thread error: {e}", exc_info=True)
            self._stop_event.wait(600)
        logger.info("🛡️ Hardened ImmuneSystem cleaner thread stopped.")

# --- Singleton ---
immune_system = ImmuneSystem()

# --- Blueprint for Management Endpoints ---
immune_bp = Blueprint("immune", __name__, url_prefix="/immune")

@immune_bp.route("/status", methods=["GET"])
@require_api_key
def immune_status():
    return jsonify({"redis_connected": immune_system.connection is not None}), http.HTTPStatus.OK

@immune_bp.route("/blacklist", methods=["POST"])
@require_api_key
def add_blacklist():
    data = request.get_json(silent=True)
    if not data or "identifier" not in data:
        return jsonify({"error": "Missing 'identifier'"}), http.HTTPStatus.BAD_REQUEST
    immune_system.add_to_blacklist(data["identifier"])
    return jsonify({"status": "success"}), http.HTTPStatus.CREATED

@immune_bp.route("/blacklist", methods=["GET"])
@require_api_key
def get_blacklist():
    with immune_system._in_memory_lock:
        bl = list(immune_system._blacklist.keys())
    return jsonify({"blacklist": bl}), http.HTTPStatus.OK

