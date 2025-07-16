import logging
import http
import secrets
from datetime import timezone
from functools import wraps

from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from sqlalchemy import func

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, ChainBlock, ApiKey, UserAccount
from peoples_coin.systems.metabolic_system import GoodwillActionSchema, validate_transaction
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

STATUS_ACCEPTED = 'accepted'
STATUS_PENDING = 'pending'
KEY_ERROR = "error"
KEY_DETAILS = "details"
KEY_MESSAGE = "message"


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-KEY")
        if not api_key:
            return jsonify({KEY_ERROR: "Missing API key"}), http.HTTPStatus.UNAUTHORIZED

        with get_session_scope(db) as session:
            key_record = session.query(ApiKey).filter_by(key=api_key, revoked=False).first()
            if not key_record:
                return jsonify({KEY_ERROR: "Invalid or revoked API key"}), http.HTTPStatus.UNAUTHORIZED
            
            # Optionally attach user info to flask.g here if needed
        return f(*args, **kwargs)
    return decorated


@api_bp.route("/create-api-key", methods=["POST"])
def create_api_key():
    """
    Creates a new API key for a user.
    Expects JSON with 'user_id' (string).
    Returns the newly generated API key.
    """
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({KEY_ERROR: "Missing 'user_id' in request body"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope(db) as session:
        user = session.query(UserAccount).filter_by(user_id=user_id).first()
        if not user:
            return jsonify({KEY_ERROR: f"User with user_id '{user_id}' not found"}), http.HTTPStatus.NOT_FOUND

        # Generate a secure random 40-character API key
        new_key = secrets.token_urlsafe(30)

        api_key_obj = ApiKey(key=new_key, user_id=user.id)
        session.add(api_key_obj)
        session.flush()

        logger.info(f"🔑 New API key created for user_id={user_id}")

        return jsonify({
            KEY_MESSAGE: "API key created successfully",
            "api_key": new_key
        }), http.HTTPStatus.CREATED


@api_bp.route("/goodwill-actions", methods=["POST"])
@require_api_key
def submit_goodwill():
    logger.info("📥 Received goodwill action POST")

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


@api_bp.route("/goodwill-history", methods=["GET"])
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


@api_bp.route("/mine-block", methods=["POST"])
@require_api_key
def mine_block():
    consensus = current_app.extensions['consensus']

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


@api_bp.route("/chain", methods=["GET"])
@require_api_key
def full_chain():
    consensus = current_app.extensions['consensus']

    with get_session_scope(db) as session:
        blocks = session.query(ChainBlock).order_by(ChainBlock.id).all()
        chain_data = []
        for block in blocks:
            chain_data.append({
                "index": block.id,
                "timestamp": block.timestamp,
                "transactions": block.transactions,
                "proof": block.nonce,
                "previous_hash": block.previous_hash,
                "hash": block.hash,
            })

    return jsonify({
        "length": len(chain_data),
        "chain": chain_data
    }), http.HTTPStatus.OK


@api_bp.route("/register-node", methods=["POST"])
@require_api_key
def register_node():
    if not request.is_json:
        return jsonify({KEY_ERROR: "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    node_address = data.get("address")
    if not node_address:
        return jsonify({KEY_ERROR: "Missing 'address' in request body"}), http.HTTPStatus.BAD_REQUEST

    consensus = current_app.extensions['consensus']
    consensus.register_node(node_address)

    logger.info(f"🌐 Node registered: {node_address}")

    return jsonify({
        KEY_MESSAGE: "Node registered successfully",
        "node": node_address
    }), http.HTTPStatus.CREATED

