# peoples_coin/routes/nervous_routes.py
import logging
import http
from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from peoples_coin.systems.immune_system import immune_system
# Import the core logic function from the system file
from peoples_coin.systems.nervous_system import process_node_data

logger = logging.getLogger(__name__)
nervous_bp = Blueprint('nervous', __name__, url_prefix='/nervous')

@nervous_bp.route("/status", methods=["GET"])
def nervous_status_endpoint():
    """Health check endpoint for the Nervous System."""
    return jsonify({"status": "success", "message": "Nervous System operational"}), http.HTTPStatus.OK

@nervous_bp.route("/receive_node_data", methods=["POST"])
@immune_system.check()
def receive_node_data_endpoint():
    """Receives and processes internal data from peer nodes."""
    if not request.is_json:
        return jsonify({"status": "error", "error": "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    try:
        raw_data = request.get_json()
        result = process_node_data(raw_data)
        return jsonify({"status": "success", "message": result["message"]}), http.HTTPStatus.ACCEPTED
    except ValidationError as ve:
        logger.warning(f"🚫 Validation failed for internal node data: {ve.errors()}")
        return jsonify({"status": "error", "error": "Invalid internal data format", "details": ve.errors()}), http.HTTPStatus.BAD_REQUEST
    except Exception:
        logger.exception("💥 Unexpected error processing internal node data.")
        return jsonify({"status": "error", "error": "Internal server error"}), http.HTTPStatus.INTERNAL_SERVER_ERROR
