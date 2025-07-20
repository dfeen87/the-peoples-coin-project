import http
from flask import Blueprint, request, jsonify
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import GoodwillAction
from peoples_coin.systems.metabolic_system import GoodwillActionSchema, validate_transaction
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_api_key
from datetime import timezone

goodwill_bp = Blueprint("goodwill", __name__, url_prefix="/api/goodwill")

KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"
STATUS_ACCEPTED = 'accepted'
STATUS_PENDING = 'pending'

@goodwill_bp.route("/actions", methods=["POST"])
@require_api_key
def submit_goodwill():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    if not data:
        return jsonify({KEY_ERROR: "No JSON data provided"}), http.HTTPStatus.BAD_REQUEST

    try:
        goodwill_data = GoodwillActionSchema(**data)
        validated_dict = goodwill_data.model_dump()
        validated_dict["timestamp"] = goodwill_data.timestamp.astimezone(timezone.utc)

        is_valid, validation_result = validate_transaction(validated_dict)
        if not is_valid:
            return jsonify({KEY_ERROR: "Transaction validation failed", KEY_DETAILS: validation_result}), http.HTTPStatus.BAD_REQUEST

        with get_session_scope(db) as session:
            goodwill_action = GoodwillAction(
                **validated_dict,
                status=STATUS_PENDING,
                resonance_score=None
            )
            session.add(goodwill_action)
            session.flush()

            return jsonify({
                KEY_MESSAGE: "Goodwill action accepted and queued.",
                "action_id": goodwill_action.id,
                "status": STATUS_ACCEPTED
            }), http.HTTPStatus.ACCEPTED

    except Exception as e:
        # You can add more fine-grained error handling here
        return jsonify({KEY_ERROR: "Internal server error", KEY_DETAILS: str(e)}), http.HTTPStatus.INTERNAL_SERVER_ERROR

@goodwill_bp.route("/summary", methods=["GET"])
@require_api_key
def goodwill_summary():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({KEY_ERROR: "Missing user_id parameter"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope(db) as session:
        total_goodwill = session.query(func.sum(GoodwillAction.resonance_score)) \
            .filter(GoodwillAction.user_id == user_id) \
            .scalar() or 0

        count = session.query(func.count(GoodwillAction.id)) \
            .filter(GoodwillAction.user_id == user_id) \
            .scalar() or 0

    return jsonify({
        "user_id": user_id,
        "total_goodwill": total_goodwill,
        "actions": count
    }), http.HTTPStatus.OK

@goodwill_bp.route("/history", methods=["GET"])
@require_api_key
def goodwill_history():
    user_id = request.args.get("user_id")
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 10))

    if not user_id:
        return jsonify({KEY_ERROR: "Missing user_id parameter"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope(db) as session:
        query = session.query(GoodwillAction) \
            .filter(GoodwillAction.user_id == user_id) \
            .order_by(GoodwillAction.timestamp.desc())

        total = query.count()
        actions = query.offset((page - 1) * size).limit(size).all()

        results = []
        for action in actions:
            results.append({
                "id": action.id,
                "action_type": action.action_type,
                "description": action.description,
                "timestamp": action.timestamp.isoformat(),
                "status": action.status,
                "resonance_score": action.resonance_score
            })

    return jsonify({
        "user_id": user_id,
        "total": total,
        "page": page,
        "size": size,
        "actions": results
    }), http.HTTPStatus.OK

