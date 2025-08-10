# peoples_coin/routes/cognitive_routes.py
import http
from flask import Blueprint, request, jsonify, Response

from peoples_coin.utils.auth import require_api_key
# Import the singleton instance from the system file
from peoples_coin.systems.cognitive_system import cognitive_system

cognitive_bp = Blueprint('cognitive_bp', __name__, url_prefix="/api/v1/cognitive")

@cognitive_bp.route('/event', methods=['POST'])
@require_api_key # **CRITICAL**: Secure this endpoint
def cognitive_event():
    """API endpoint to accept new events for processing."""
    event = request.get_json()
    if not event or not isinstance(event, dict) or "type" not in event:
        return jsonify({"error": "Event must be a JSON object with a 'type' field."}), http.HTTPStatus.BAD_REQUEST

    # Attempt to publish to the durable RabbitMQ queue first
    if cognitive_system.publish_event(event):
        return jsonify({"message": "Event published for processing."}), http.HTTPStatus.ACCEPTED
    else:
        # Fallback to in-memory if RabbitMQ is unavailable
        cognitive_system.enqueue_event(event)
        return jsonify({"message": "Event accepted for local processing (broker unavailable)."}), http.HTTPStatus.ACCEPTED
