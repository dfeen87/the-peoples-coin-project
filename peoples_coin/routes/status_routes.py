# peoples_coin/routes/status_routes.py
import http
from flask import Blueprint, jsonify, request

# Import the core logic functions from your system file
from peoples_coin.systems.status import get_backend_status, get_recent_events

status_bp = Blueprint('status_bp', __name__)

@status_bp.route('/api/backend-status', methods=['GET'])
def backend_status_endpoint():
    """Returns the aggregated health status of all backend systems."""
    # The get_backend_status function provides an overall system health,
    # so the transaction_id parameter is not needed here.
    status = get_backend_status()
    
    # Determine the overall HTTP status code based on health
    status_code = http.HTTPStatus.OK if status.get("systemHealthy") else http.HTTPStatus.SERVICE_UNAVAILABLE
    
    return jsonify(status), status_code

@status_bp.route('/api/backend-events', methods=['GET'])
def backend_events_endpoint():
    """Returns a list of recent backend events."""
    try:
        limit = request.args.get('limit', default=50, type=int)
        # Enforce a reasonable maximum limit to prevent abuse
        limit = min(limit, 200) 
        events = get_recent_events(limit)
        return jsonify(events), http.HTTPStatus.OK
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid 'limit' parameter"}), http.HTTPStatus.BAD_REQUEST
