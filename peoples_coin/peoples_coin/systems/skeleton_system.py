import os
import logging
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, request, jsonify, abort, g, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis, RedisError

# --- RECOMMENDED: Configure logging at the module level ---
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# --- Import other project modules ---
# Assuming these exist in your project structure
# from peoples_coin import did_registry, consensus, validation

# ===== Factory Function to Create Flask App Instance =====
def create_skeleton_app():
    """Factory to create and configure the Skeleton System Flask application."""
    app = Flask(__name__)

    app.config.update(
        API_KEYS=set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(",")),
        RATELIMIT_DEFAULT="50 per hour;10 per minute",
        DEBUG=os.getenv('SKELETON_DEBUG', 'false').lower() == 'true',
    )
    logger.info(f"Skeleton System: Debug mode = {app.config['DEBUG']}")

    # Setup rate limiter with Redis fallback
    try:
        redis_uri = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{int(os.getenv('REDIS_PORT', 6379))}/{int(os.getenv('REDIS_DB_SKELETON', 2))}"
        # Test connection before initializing limiter with URI
        Redis.from_url(redis_uri, socket_connect_timeout=2).ping()
        limiter = Limiter(key_func=get_remote_address, storage_uri=redis_uri)
        app.logger.info("Skeleton System: Using Redis backend for rate limiting.")
    except (RedisError, Exception) as e:
        limiter = Limiter(key_func=get_remote_address)
        app.logger.warning(f"Skeleton System: Redis unavailable, falling back to in-memory rate limiting. Error: {e}")
    limiter.init_app(app)

    # ===== Global Request Hook for Authentication =====
    @app.before_request
    def before_request_hook():
        # Skip auth check for public endpoints like health checks
        if request.endpoint in ('index', 'health'):
            return

        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key not in current_app.config["API_KEYS"]:
            logger.warning(f"Unauthorized access attempt from {request.remote_addr} with key: {api_key}")
            abort(401, description="Invalid or missing API key")

        g.api_key = api_key # Store key for logging purposes
        logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

    # ===== Error handlers =====
    # (Error handlers remain the same - they are already well-implemented)
    @app.errorhandler(401)
    def handle_unauthorized(e):
        return jsonify(error=getattr(e, 'description', 'Unauthorized')), 401
    
    # ... other error handlers (400, 404, 429, 500) ...

    # ===== Routes =====
    @app.route("/")
    def index():
        return jsonify({"message": "Welcome to The People's Coin Skeleton System"})

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="Skeleton System operational", timestamp=datetime.now(timezone.utc).isoformat())

    @app.route("/register_node", methods=["POST"])
    @limiter.limit("10 per minute")
    def register():
        # No @require_api_key needed, the before_request hook handles it.
        node_info = request.get_json()
        if not node_info:
            abort(400, "Invalid or missing JSON body")
        # result = did_registry.register_node(node_info)
        # logger.info(f"Node registered: {node_info.get('node_id')} by key: {g.api_key}")
        # return jsonify(result), 201
        return jsonify({"status": "ok - node registered (stub)"}), 201 # Placeholder

    @app.route("/nodes", methods=["GET"])
    @limiter.limit("20 per minute")
    def list_nodes():
        # nodes = did_registry.get_all_nodes()
        # return jsonify(nodes), 200
        return jsonify([{"node_id": "node1_stub"}, {"node_id": "node2_stub"}]), 200 # Placeholder
    
    # ... other routes (/validate_transaction, /consensus/status) would also have the decorator removed ...

    return app

# ===== Direct Execution Block =====
if __name__ == "__main__":
    skeleton_app = create_skeleton_app()
    port = int(os.environ.get("SKELETON_PORT", 5002))
    logger.info(f"Starting Skeleton System API on http://0.0.0.0:{port}")
    # use_reloader should be False for production or when running background tasks
    skeleton_app.run(host="0.0.0.0", port=port, use_reloader=False)
