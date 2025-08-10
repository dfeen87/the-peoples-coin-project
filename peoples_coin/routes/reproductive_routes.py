# peoples_coin/routes/reproductive_routes.py
import logging
import http
import uuid
from decimal import Decimal

from flask import Blueprint, request, jsonify, g

from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.utils.validation import validate_with
# This should point to a dedicated service layer, not the system itself
from peoples_coin.services.governance_service import governance_service, ProposalError
from .schemas import CreateProposalSchema, SubmitVoteSchema

logger = logging.getLogger(__name__)
reproductive_bp = Blueprint('reproductive', __name__, url_prefix='/api/v1/governance')


@reproductive_bp.route('/proposals', methods=['POST'])
@require_firebase_token
@validate_with(CreateProposalSchema)
def create_proposal():
    """Creates a new proposal."""
    proposal_data = g.validated_data
    proposer_user_id = g.user.id
    try:
        new_proposal = governance_service.create_new_proposal(
            proposer_user_id=proposer_user_id,
            proposal_data=proposal_data.model_dump()
        )
        return jsonify({"status": "success", "proposal": new_proposal}), http.HTTPStatus.CREATED
    except ProposalError as e:
        return jsonify({"status": "error", "error": str(e)}), http.HTTPStatus.BAD_REQUEST
    except Exception:
        logger.exception("Unexpected error creating proposal.")
        return jsonify({"status": "error", "error": "Internal server error"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@reproductive_bp.route('/proposals/<uuid:proposal_id>/vote', methods=['POST'])
@require_firebase_token
@validate_with(SubmitVoteSchema)
def submit_vote(proposal_id: uuid.UUID):
    """Submits a vote on a proposal."""
    vote_data = g.validated_data
    voter_user_id = g.user.id
    try:
        vote_result = governance_service.submit_user_vote(
            proposal_id=proposal_id,
            voter_user_id=voter_user_id,
            vote_data=vote_data.model_dump()
        )
        return jsonify({"status": "success", "vote": vote_result}), http.HTTPStatus.CREATED
    except ProposalError as e:
        status_code = http.HTTPStatus.BAD_REQUEST
        if "not found" in str(e): status_code = http.HTTPStatus.NOT_FOUND
        if "already voted" in str(e): status_code = http.HTTPStatus.CONFLICT
        return jsonify({"status": "error", "error": str(e)}), status_code
    except Exception:
        logger.exception("Unexpected error submitting vote.")
        return jsonify({"status": "error", "error": "Internal server error"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@reproductive_bp.route('/proposals', methods=['GET'])
def list_proposals():
    """Lists all proposals, with optional filtering."""
    status_filter = request.args.get('status')
    proposals = governance_service.get_all_proposals(status=status_filter)
    return jsonify({"status": "success", "proposals": proposals}), http.HTTPStatus.OK


@reproductive_bp.route('/proposals/<uuid:proposal_id>', methods=['GET'])
def get_proposal_details(proposal_id: uuid.UUID):
    """Gets detailed information for a single proposal."""
    proposal_details = governance_service.get_proposal_by_id(proposal_id)
    if not proposal_details:
        return jsonify({"status": "error", "error": "Proposal not found"}), http.HTTPStatus.NOT_FOUND
    return jsonify({"status": "success", "proposal": proposal_details}), http.HTTPStatus.OK
