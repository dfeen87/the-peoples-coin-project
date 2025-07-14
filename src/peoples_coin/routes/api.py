import logging
import http
from datetime import timezone

from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from sqlalchemy import func

from ..db.db_utils import get_session_scope
from ..db.models import GoodwillAction
from ..systems.metabolic_system import GoodwillActionSchema, validate_transaction
from ..consensus import Consensus
from ..extensions import db

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

STATUS_ACCEPTED = 'accepted'
STATUS_PENDING = 'pending'
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"

# Remove consensus instance here; it is now managed in __init__.py

@api_bp.route("/goodwill-actions", methods=["POST"])
def submit_goodwill():
    """
    Accepts a goodwill action and persists it.
    """
    logger.info("📥 Received goodwill action POST")

    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    if not data:
        return jsonify({KEY_ERROR: "No JSON data provided"}), http.HTTPStatus.BAD_REQUEST

    try:
        # Validate payload schema
        goodwill_data = GoodwillActionSchema(**data)
        validated_dict = goodwill_data.model_dump()
        validated_dict["timestamp"] = goodwill_data.timestamp.astimezone(timezone.utc)

        # Business validation
        is_valid, validation_result = validate_transaction(validated_dict)
        if not is_valid:
            return jsonify({KEY_ERROR: "Transaction validation failed", KEY_DETAILS: validation_result}), http.HTTPStatus.BAD_REQUEST

        # Persist
        with get_session_scope(db) as session:
            goodwill_action = GoodwillAction(
                **validated_dict,
                status=STATUS_PENDING,
                resonance_score=None
            )
            session.add(goodwill_action)
            session.flush()

            logger.info(f"💾 GoodwillAction ID {goodwill_action.id} queued.")

            return jsonify({
                KEY_MESSAGE: "Goodwill action accepted and queued.",
                "action_id": goodwill_action.id,
                "status": STATUS_ACCEPTED
            }), http.HTTPStatus.ACCEPTED

    except ValidationError as ve:
        return jsonify({KEY_ERROR: "Invalid data", KEY_DETAILS: ve.errors()}), http.HTTPStatus.BAD_REQUEST

    except Exception as e:
        logger.exception("Unexpected error during goodwill submission")
        return jsonify({KEY_ERROR: "Internal server error", KEY_DETAILS: str(e)}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@api_bp.route("/goodwill-summary", methods=["GET"])
def goodwill_summary():
    """
    Returns a summary of goodwill for a given user_id.
    """
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


@api_bp.route("/goodwill-history", methods=["GET"])
def goodwill_history():
    """
    Returns paginated history of goodwill actions for a user.
    """
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


@api_bp.route("/mine-block", methods=["POST"])
def mine_block():
    """
    Triggers mining of a new block with current transactions.
    """
    # Access consensus via current_app if needed, or import & instantiate properly elsewhere
    from ..consensus import Consensus
    consensus = Consensus()

    last_block = consensus.last_block()
    last_proof = last_block.nonce if last_block else 0
    proof = consensus.proof_of_work(last_proof)
    block = consensus.new_block(proof)

    with get_session_scope(db) as session:
        session.add(block)
        session.flush()

    logger.info(f"⛏️ Mined new block with hash: {block.hash}")
    return jsonify({
        "message": "New block mined",
        "block_hash": block.hash,
        "block_id": block.id,
        "timestamp": block.timestamp
    }), http.HTTPStatus.CREATED

