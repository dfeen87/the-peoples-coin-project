import os
import logging
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, request, jsonify, abort, g, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis, RedisError

# --- Import modules relative to the 'peoples_coin.peoples_coin' package ---
from peoples_coin import did_registry
from peoples_coin import consensus
from peoples_coin import validation

# --- Setup logging for this specific microservice ---
logger = logging.getLogger(__name__)

# ===== Factory Function to Create Flask App Instance =====
def create_skeleton_app():
    """
    Factory function to create and configure the Skeleton System Flask application.
    This prevents the app from being instantiated on module import.
    """
    app = Flask(__name__)

    # --- Configuration for this specific microservice ---
    app.config.update(
        API_KEYS=set(os.getenv("SKELETON_API_KEYS", "skeletonkey,defaultkey").split(",")),
        RATELIMIT_DEFAULT="50 per hour;10 per minute",
        DEBUG=os.getenv('SKELETON_DEBUG', 'true').lower() == 'true',
    )

    logger.info(f"Skeleton System: Debug mode = {app.config['DEBUG']}")
    logger.info(f"Skeleton System: Loaded API Keys: {list(app.config['API_KEYS'])}")

    # Setup rate limiter for this specific microservice
    try:
        redis_conn = Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB_SKELETON', 2)), # Use a distinct Redis DB
            decode_responses=True,
            socket_connect_timeout=2
        )
        redis_conn.ping()
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=f"redis://{redis_conn.connection_pool.connection_kwargs['host']}:{redis_conn.connection_pool.connection_kwargs['port']}/{redis_conn.connection_pool.connection_kwargs['db']}"
        )
        app.logger.info("Skeleton System: Using Redis backend for rate limiting.")
    except (RedisError, Exception) as e:
        limiter = Limiter(key_func=get_remote_address)
        app.logger.warning(f"Skeleton System: Redis not available, falling back to in-memory rate limiting. Error: {e}")
    limiter.init_app(app)

    # ===== API key decorator (local to this microservice) =====
    def require_api_key(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            api_key = request.headers.get("X-API-Key")
            if not api_key or api_key not in current_app.config["API_KEYS"]:
                current_app.logger.warning(
                    f"Skeleton System: Unauthorized access attempt from {request.remote_addr} to {request.path} with API key: {api_key}"
                )
                abort(401, description="Invalid or missing API key")
            g.api_key = api_key
            return f(*args, **kwargs)
        return decorated

    # ===== Global before request hook (local to this microservice) =====
    @app.before_request
    def before_request_hook():
        if request.endpoint not in ('index', 'health'):
            api_key = request.headers.get("X-API-Key")
            if not api_key or api_key not in current_app.config["API_KEYS"]:
                current_app.logger.warning(
                    f"Skeleton System: Unauthorized access attempt from {request.remote_addr} to {request.path} with API key: {api_key}"
                )
                abort(401, description="Invalid or missing API key")
        current_app.logger.info(f"Skeleton System Request: {request.method} {request.path} from {request.remote_addr}")

    # ===== Error handlers (local to this microservice) =====
    @app.errorhandler(400)
    def handle_bad_request(e):
        current_app.logger.error(f"Skeleton System 400 Bad Request: {e.description}")
        return jsonify(error=e.description), 400

    @app.errorhandler(401)
    def handle_unauthorized(e):
        current_app.logger.error(f"Skeleton System 401 Unauthorized: {e.description}")
        return jsonify(error=e.description), 401

    @app.errorhandler(404)
    def handle_not_found(e):
        current_app.logger.error(f"Skeleton System 404 Not Found: {request.path}")
        return jsonify(error="Endpoint not found"), 404

    @app.errorhandler(429)
    def handle_rate_limit(e):
        current_app.logger.warning(f"Skeleton System Rate limit exceeded from {request.remote_addr} to {request.path}")
        return jsonify(error="Rate limit exceeded. Please try again later."), 429

    @app.errorhandler(500)
    def handle_internal_error(e):
        current_app.logger.error(f"Skeleton System 500 Internal Server Error: {str(e)}", exc_info=True)
        return jsonify(error="Internal server error"), 500

    # ===== Health check =====
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="Skeleton System operational", timestamp=str(datetime.now(timezone.utc))), 200

    # ===== Routes for Skeleton System Microservice =====
    @app.route("/")
    def index():
        return jsonify({"message": "Welcome to The People's Coin Skeleton System"}), 200

    @app.route("/register_node", methods=["POST"])
    @require_api_key
    @limiter.limit("10 per minute")
    def register():
        try:
            node_info = request.get_json(force=True)
        except Exception:
            abort(400, description="Invalid JSON body")

        if not node_info:
            abort(400, description="Missing node info")

        try:
            result = did_registry.register_node(node_info)
            current_app.logger.info(f"Skeleton System: Node registered: {node_info.get('node_id', 'unknown')} by API key: {g.api_key}")
            return jsonify(result), 201
        except Exception as e:
            current_app.logger.error(f"Skeleton System: Error registering node: {e}", exc_info=True)
            abort(500, description="Failed to register node")

    @app.route("/nodes", methods=["GET"])
    @require_api_key
    @limiter.limit("20 per minute")
    def list_nodes():
        try:
            nodes = did_registry.get_all_nodes()
            return jsonify(nodes), 200
        except Exception as e:
            current_app.logger.error(f"Skeleton System: Error listing nodes: {e}", exc_info=True)
            abort(500, description="Failed to fetch nodes")

    @app.route("/validate_transaction", methods=["POST"])
    @require_api_key
    @limiter.limit("30 per minute")
    def validate():
        try:
            tx = request.get_json(force=True)
        except Exception:
            abort(400, description="Invalid JSON body")

        if not tx:
            abort(400, description="Missing transaction data")

        try:
            is_valid, details = validation.validate_transaction(tx)
            response = {"valid": is_valid, "details": details}
            current_app.logger.info(f"Skeleton System: Transaction validation result: {is_valid} by API key: {g.api_key}")
            return jsonify(response), 200
        except Exception as e:
            current_app.logger.error(f"Skeleton System: Error validating transaction: {e}", exc_info=True)
            abort(500, description="Failed to validate transaction")

    @app.route("/consensus/status", methods=["GET"])
    @require_api_key
    @limiter.limit("10 per minute")
    def consensus_status():
        try:
            status = consensus.get_consensus_status()
            return jsonify(status), 200
        except Exception as e:
            current_app.logger.error(f"Skeleton System: Error getting consensus status: {e}", exc_info=True)
            abort(500, description="Failed to fetch consensus status")

    return app # Return the configured Flask app instance

# This block ensures the app runs when this file is executed directly
if __name__ == "__main__":
    skeleton_app = create_skeleton_app()
    logging.basicConfig(
        level=logging.DEBUG if skeleton_app.config['DEBUG'] else logging.INFO,
        format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
    )
    port = int(os.environ.get("SKELETON_PORT", 5002))
    logger.info(f"Starting Skeleton System API on port {port}")
    skeleton_app.run(host="0.0.0.0", port=port, debug=skeleton_app.config['DEBUG'], use_reloader=False)

