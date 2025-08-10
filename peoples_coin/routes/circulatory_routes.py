# peoples_coin/routes/circulatory_routes.py

import http
import uuid
from flask import Blueprint, jsonify

from peoples_coin.utils.auth import require_api_key
# Import the singleton instance from the system file
from peoples_coin.systems.circulatory_system import circulatory_system

circulatory_bp = Blueprint('circulatory', __name__, url_prefix='/circulatory')

@circulatory_bp.route('/mint_goodwill/<string:goodwill_action_id>', methods=['POST'])
@require_api_key # Secure this critical endpoint
def mint_goodwill(goodwill_action_id):
    """Triggers token minting for a verified GoodwillAction by its UUID."""
    try:
        action_uuid = uuid.UUID(goodwill_action_id)
    except ValueError:
        return jsonify({"status": "error", "error": "Invalid goodwill_action_id UUID format"}), http.HTTPStatus.BAD_REQUEST

    success, message, status_code = circulatory_system.process_goodwill_for_minting(action_uuid)

    if success:
        return jsonify({"status": "success", "message": message}), status_code
    else:
        return jsonify({"status": "error", "error": message}), status_code

@circulatory_bp.route('/status', methods=['GET'])
def status_endpoint():
    """API health check for the Circulatory System."""
    status_info = get_circulatory_status()
    status_code = http.HTTPStatus.OK if status_info["healthy"] else http.HTTPStatus.SERVICE_UNAVAILABLE
    return jsonify(status_info), status_code
