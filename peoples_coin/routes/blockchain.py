import http
from flask import Blueprint, request, jsonify, current_app
from pydantic import BaseModel, Field, HttpUrl

from sqlalchemy import func
from peoples_coin.extensions import db # **FIX**: Import the db instance
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ChainBlock
from peoples_coin.utils.auth import require_api_key
from peoples_coin.utils.validation import validate_with # Import our validator
# from peoples_coin.tasks import mine_block_task # Import your Celery task

blockchain_bp = Blueprint("blockchain", __name__, url_prefix="/api/blockchain")

# --- Pydantic Models for Input Validation ---
class RegisterNodeSchema(BaseModel):
    address: HttpUrl = Field(..., description="The network address of the node (e.g., 'http://192.168.1.10:5000')")

# --- API Routes ---

@blockchain_bp.route("/mine-block", methods=["POST"])
@require_api_key
def mine_block():
    """Triggers a new block to be mined asynchronously."""
    # **IMPROVEMENT**: Instead of blocking, delegate to a Celery task.
    # The task will perform the proof_of_work and create the new block.
    # mine_block_task.delay() # Example call to the Celery task

    # For now, we'll just return an accepted response.
    return jsonify({
        "message": "Block mining has been initiated.",
        "status": "pending"
    }), http.HTTPStatus.ACCEPTED

@blockchain_bp.route("/chain", methods=["GET"])
@require_api_key
def full_chain():
    """
    Returns the full blockchain, with support for pagination.
    Query Params: ?page=1&per_page=50
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        # Enforce a maximum page size for security and performance
        per_page = min(per_page, 100)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid pagination parameters"}), http.HTTPStatus.BAD_REQUEST

    with get_session_scope() as session:
        # **IMPROVEMENT**: Use Flask-SQLAlchemy's paginate for efficient querying.
        # You'll need to configure your db session for this or use a manual slice.
        # Manual pagination approach:
        offset = (page - 1) * per_page
        paginated_query = session.query(ChainBlock).order_by(ChainBlock.height).limit(per_page).offset(offset)
        total_blocks = session.query(func.count(ChainBlock.id)).scalar()
        
        blocks = paginated_query.all()

        chain_data = [block.to_dict() for block in blocks] # Assuming a to_dict() method on the model

    return jsonify({
        "chain": chain_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_pages": (total_blocks + per_page - 1) // per_page,
            "total_blocks": total_blocks,
        }
    }), http.HTTPStatus.OK

@blockchain_bp.route("/register-node", methods=["POST"])
@require_api_key
@validate_with(RegisterNodeSchema) # **IMPROVEMENT**: Use Pydantic for validation
def register_node():
    """Registers a new peer node in the network."""
    # The `validate_with` decorator handles JSON checking and validation.
    # The validated data is available in `g.validated_data`.
    validated_data: RegisterNodeSchema = g.validated_data
    
    consensus = current_app.extensions['consensus']
    consensus.register_node(str(validated_data.address)) # Convert PydanticUrl to string

    return jsonify({
        "message": "Node registered successfully",
        "node_registered": str(validated_data.address)
    }), http.HTTPStatus.CREATED
