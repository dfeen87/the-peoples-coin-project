import http
from flask import Blueprint, request, jsonify, current_app
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import ChainBlock
from peoples_coin.utils.auth import require_api_key

blockchain_bp = Blueprint("blockchain", __name__, url_prefix="/api/blockchain")

@blockchain_bp.route("/mine-block", methods=["POST"])
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

    return jsonify({
        "message": "New block mined",
        "block_hash": block.hash,
        "block_id": block.id,
        "timestamp": block.timestamp
    }), http.HTTPStatus.CREATED

@blockchain_bp.route("/chain", methods=["GET"])
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

@blockchain_bp.route("/register-node", methods=["POST"])
@require_api_key
def register_node():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    data = request.get_json()
    node_address = data.get("address")
    if not node_address:
        return jsonify({"error": "Missing 'address' in request body"}), http.HTTPStatus.BAD_REQUEST

    consensus = current_app.extensions['consensus']
    consensus.register_node(node_address)

    return jsonify({
        "message": "Node registered successfully",
        "node": node_address
    }), http.HTTPStatus.CREATED

