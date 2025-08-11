import logging
import http
import uuid
from decimal import Decimal
from typing import Tuple

from flask import Blueprint, request, jsonify, Response, g
from pydantic import BaseModel, Field
from typing_extensions import Literal

# Use our standard, secure decorators
from peoples_coin.utils.auth import require_firebase_token
from peoples_coin.utils.validation import validate_with

# Import your services and custom exceptions
from peoples_coin.services.governance_service import governance_service, ProposalError
from peoples_coin.models import Proposal, Vote # For type hints

logger = logging.getLogger(__name__)
governance_bp = Blueprint('governance', __name__, url_prefix='/api/v1/governance')

# --- Pydantic Input Models ---
# The schema classes are defined here, not imported from a separate file.
class CreateProposalSchema(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=20)
    proposal_type: str
    details: dict = Field(default_factory=dict)

class SubmitVoteSchema(BaseModel):
    vote_choice: str = Field(..., pattern=r"^(YES|NO|ABSTAIN)$")
    vote_weight: Decimal = Field(..., gt=Decimal('0.0'))

# --- API Routes ---

@governance_bp.route('/proposals', methods=['POST'])
@require_firebase_token
@validate_with(CreateProposalSchema)
def create_proposal() -> Tuple[Response, int]:
    """Creates a new proposal, authored by the authenticated user."""
    proposal_data: CreateProposalSchema = g.validated_data
    proposer_user_id = g.user.id
    logger.info(f"📥 API: Received proposal creation request from user: {proposer_user_id}")

    try:
        new_proposal = governance_service.create_new_proposal(
            proposer_user_id=proposer_user_id,
            proposal_data=proposal_data.model_dump()
        )
        return jsonify({
            "status": "success",
            "message": "Proposal created successfully.",
            "proposal": new_proposal
        }), http.HTTPStatus.CREATED
    except ProposalError as e:
        logger.warning(f"🚫 API: Proposal creation failed for user {proposer_user_id}. Reason: {e}")
        return jsonify({"status": "error", "error": str(e)}), http.HTTPStatus.BAD_REQUEST
    except Exception as e:
        logger.exception(f"💥 API: Unexpected error creating proposal for user {proposer_user_id}.")
        return jsonify({"status": "error", "error": "An internal server error occurred."}), http.HTTPStatus.INTERNAL_SERVER_ERROR

@governance_bp.route('/proposals/<uuid:proposal_id>/vote', methods=['POST'])
@require_firebase_token
@validate_with(SubmitVoteSchema)
def submit_vote(proposal_id: uuid.UUID) -> Tuple[Response, int]:
    """Submits a vote on a proposal for the authenticated user."""
    vote_data: SubmitVoteSchema = g.validated_data
    voter_user_id = g.user.id

    logger.info(f"📥 API: Received vote for proposal {proposal_id} from user {voter_user_id}.")

    try:
        vote_result = governance_service.submit_user_vote(
            proposal_id=proposal_id,
            voter_user_id=voter_user_id,
            vote_data=vote_data.model_dump()
        )
        return jsonify({
            "status": "success",
            "message": "Vote submitted successfully.",
            "vote": vote_result
        }), http.HTTPStatus.CREATED
    except ProposalError as e:
        logger.warning(f"🚫 API: Vote submission failed for user {voter_user_id} on proposal {proposal_id}. Reason: {e}")
        status_code = http.HTTPStatus.BAD_REQUEST
        if "not found" in str(e): status_code = http.HTTPStatus.NOT_FOUND
        if "already voted" in str(e): status_code = http.HTTPStatus.CONFLICT
        if "Insufficient balance" in str(e): status_code = http.HTTPStatus.FORBIDDEN
        return jsonify({"status": "error", "error": str(e)}), status_code
    except Exception as e:
        logger.exception(f"💥 API: Unexpected error submitting vote for user {voter_user_id} on proposal {proposal_id}.")
        return jsonify({"status": "error", "error": "An internal server error occurred."}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@governance_bp.route('/proposals', methods=['GET'])
def list_proposals() -> Tuple[Response, int]:
    """Lists all proposals, with optional filtering."""
    status_filter = request.args.get('status')
    proposals = governance_service.get_all_proposals(status=status_filter)
    return jsonify({"status": "success", "proposals": proposals}), http.HTTPStatus.OK


@governance_bp.route('/proposals/<uuid:proposal_id>', methods=['GET'])
def get_proposal_details(proposal_id: uuid.UUID) -> Tuple[Response, int]:
    """Gets detailed information for a single proposal."""
    proposal_details = governance_service.get_proposal_by_id(proposal_id)
    if not proposal_details:
        return jsonify({"status": "error", "error": "Proposal not found"}), http.HTTPStatus.NOT_FOUND
    return jsonify({"status": "success", "proposal": proposal_details}), http.HTTPStatus.OK


@governance_bp.route('/council_members', methods=['GET'])
def list_council_members() -> Tuple[Response, int]:
    """Lists all council members, with optional filtering."""
    role_filter = request.args.get('role')
    members = governance_service.get_council_members(role=role_filter)
    return jsonify({"status": "success", "council_members": members}), http.HTTPStatus.OK
