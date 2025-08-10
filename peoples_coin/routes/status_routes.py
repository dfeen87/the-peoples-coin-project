# peoples_coin/routes/status_routes.py

from flask import Blueprint, jsonify, request
from system.status import get_backend_status, get_recent_events

status_bp = Blueprint('status_bp', __name__)

@status_bp.route('/api/backend-status', methods=['GET'])
def backend_status():
    # Optional query param: transaction_id
    txn_id = request.args.get('transaction_id', None)
    status = get_backend_status(txn_id)
    return jsonify(status)

@status_bp.route('/api/backend-events', methods=['GET'])
def backend_events():
    # Optional query param: limit (default 50)
    limit = request.args.get('limit', default=50, type=int)
    events = get_recent_events(limit)
    return jsonify(events)

