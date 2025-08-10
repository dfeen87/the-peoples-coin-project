# peoples_coin/routes/immune_routes.py

import http
from flask import Blueprint, request, jsonify

from peoples_coin.utils.auth import require_api_key
# Import the singleton instance from the system file
from peoples_coin.systems.immune_system import immune_system

immune_bp = Blueprint("immune", __name__, url_prefix="/immune")

@immune_bp.route("/status", methods=["GET"])
@require_api_key
def immune_status_endpoint():
    """Returns basic status of the immune system."""
    status = { "redis_connected": immune_system.connection is not None }
    return jsonify(status), http.HTTPStatus.OK

@immune_bp.route("/blacklist", methods=["POST"])
@require_api_key
def add_to_blacklist_endpoint():
    """Adds an identifier to the blacklist."""
    data = request.get_json(silent=True)
    if not data or "identifier" not in data:
        return jsonify({"error": "Missing 'identifier' in request body"}), http.HTTPStatus.BAD_REQUEST

    identifier = data["identifier"]
    immune_system.add_to_blacklist(identifier)
    return jsonify({"status": "success", "blacklisted": identifier}), http.HTTPStatus.CREATED

@immune_bp.route("/blacklist", methods=["GET"])
@require_api_key
def get_blacklist_endpoint():
    """Returns the list of currently blacklisted identifiers."""
    blacklist = []
    if immune_system.connection:
        try:
            blacklist = list(immune_system.connection.smembers("immune:blacklist"))
        except Exception as e:
            return jsonify({"error": "Failed to retrieve from Redis"}), http.HTTPStatus.INTERNAL_SERVER_ERROR
    else:
        with immune_system._in_memory_lock:
            blacklist = list(immune_system._blacklist.keys())

    return jsonify({"blacklist": blacklist}), http.HTTPStatus.OK
