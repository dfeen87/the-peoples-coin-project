import http
from flask import Blueprint, request, jsonify, current_app, g
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from sqlalchemy import func
from peoples_coin.extensions import db  # Make sure this is your Flask-SQLAlchemy instance
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import ChainBlock
from peoples_coin.utils.auth import require_api_key
from peoples_coin.utils.validation import validate_with
# from peoples_coin.tasks import mine_block_task  # Uncomment when ready to use Celery task

blockchain_bp = Blueprint("blockchain", __name__, url_prefix="/api/blockchain")


# --- Pydantic Model for Node Registration ---
class RegisterNodeSchema(BaseModel):
    address: HttpUrl = Field(
        ...,
        description="The network address of the node (e.g., 'http://192.168.1.10:5000')"
    )


# --- API Endpoints ---


@blockchain_bp.route("/mine-block", methods=["POST"])
@require_api_key
def mine_block():
    """
    Endpoint to trigger asynchronous mining of a new block.
    Delegates actual mining to a background Celery task for non-blocking behavior.
    """
    # Uncomment when Celery task is ready
    # mine_block_task.delay()

    return jsonify({
        "message": "Block mining has been initiated.",
        "status": "pending"
    }), http.HTTPStatus.ACCEPTED


@blockchain_bp.route("/chain", methods=["GET"])
@require_api_key
def full_chain():
    """
    Returns the blockchain with pagination support.
    Query parameters:
        - page (int): Page number, defaults to 1
        - per_page (int): Number of blocks per page, max 100, defaults to 50
    """
    try:
        page = request.args.get('page', default=1, type=int)
        per_page = request.args.get('per_page', default=50, type=int)
        per_page = min(per_page, 100)
        if page < 1 or per_page < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid pagination parameters. 'page' and 'per_page' must be positive integers."}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope() as session:
        offset = (page - 1) * per_page
        paginated_query = session.query(ChainBlock).order_by(ChainBlock.height).limit(per_page).offset(offset)
        total_blocks = session.query(func.count(ChainBlock.id)).scalar()

        blocks = paginated_query.all()
        chain_data = [block.to_dict() for block in blocks]  # Ensure to_dict() is implemented on ChainBlock

    total_pages = (total_blocks + per_page - 1) // per_page if total_blocks else 0

    return jsonify({
        "chain": chain_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_blocks": total_blocks,
        }
    }), http.HTTPStatus.OK


@blockchain_bp.route("/register-node", methods=["POST"])
@require_api_key
@validate_with(RegisterNodeSchema)
def register_node():
    """
    Register a new peer node.
    Expects JSON body with 'address' field validated via Pydantic.
    """
    validated_data: RegisterNodeSchema = g.validated_data

    consensus = current_app.extensions.get('consensus')
    if not consensus:
        return jsonify({"error": "Consensus service is not available"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

    consensus.register_node(str(validated_data.address))

    return jsonify({
        "message": "Node registered successfully",
        "node_registered": str(validated_data.address)
    }), http.HTTPStatus.CREATED

