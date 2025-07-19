import logging
import http
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
from decimal import Decimal

from flask import Blueprint, request, jsonify, Response, Flask, g, current_app
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

# Import service instances
from peoples_coin.services.governance_service import governance_service
from peoples_coin.services.user_service import user_service

# Original imports remain
from peoples_coin.extensions import db
from peoples_coin.systems.immune_system import immune_system

from peoples_coin.utils.validation.validation import validate_with

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import Proposal, Vote, UserAccount, CouncilMember 

logger = logging.getLogger(__name__)

# --- Constants ---
STATUS_PROPOSAL_DRAFT = 'DRAFT'
STATUS_PROPOSAL_VOTING = 'VOTING'
STATUS_PROPOSAL_PASSED = 'PASSED'
STATUS_PROPOSAL_FAILED = 'FAILED'
STATUS_PROPOSAL_EXECUTED = 'EXECUTED'

VOTE_CHOICE_YES = 'YES'
VOTE_CHOICE_NO = 'NO'
VOTE_CHOICE_ABSTAIN = 'ABSTAIN'

# ==============================================================================
# 1. Pydantic Input Models
# ==============================================================================

class CreateProposalSchema(BaseModel):
    proposer_user_id: str = Field(..., description="Firebase UID of the user proposing")
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=20)
    proposal_type: str = Field(..., description="Type of proposal (e.g., PROTOCOL_CHANGE, TREASURY_SPEND)")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Specific parameters for the proposal")
    
    vote_duration_days: Optional[int] = Field(None, ge=1, le=30, description="Duration in days for voting period")
    required_quorum: Optional[Decimal] = Field(None, ge=Decimal('0.0'), le=Decimal('1.0'), 
                                               description="Required quorum as a decimal (e.g., 0.5 for 50%)")

    @field_validator('proposer_user_id')
    @classmethod
    def validate_proposer_user_id(cls, v: str) -> str:
        # In a real system, you'd verify this user_id exists in your UserAccount DB
        # Authentication middleware should confirm it's the current user.
        return v

class SubmitVoteSchema(BaseModel):
    proposal_id: str = Field(..., description="ID of the proposal being voted on")
    voter_user_id: str = Field(..., description="Firebase UID of the user casting the vote")
    vote_choice: str = Field(..., pattern=f"^{VOTE_CHOICE_YES}|{VOTE_CHOICE_NO}|{VOTE_CHOICE_ABSTAIN}$")
    vote_weight: Decimal = Field(..., gt=Decimal('0.0'), description="Raw voting power (loves) allocated to this vote")

    @field_validator('voter_user_id')
    @classmethod
    def validate_voter_user_id(cls, v: str) -> str:
        # Similar to proposer_user_id, verify existence in UserAccount DB
        return v

# ==============================================================================
# 2. Reproductive System Logic Class (Now primarily called by API endpoints)
# ==============================================================================

class ReproductiveSystem:
    """
    Manages governance features: proposals, voting, and DAO councils.
    The actual business logic methods are typically called by the API endpoints
    or background workers.
    """
    def __init__(self):
        self.app: Optional[Flask] = None
        self.db = None
        self._initialized = False
        logger.info("🌱 ReproductiveSystem instance created.")

    def init_app(self, app: Flask, db_instance):
        if self._initialized:
            logger.warning("⚠️ ReproductiveSystem already initialized.")
            return

        self.app = app
        self.db = db_instance
        self._initialized = True
        logger.info("🌱 ReproductiveSystem initialized and configured.")

    def calculate_quadratic_vote_power(self, raw_vote_weight: Decimal) -> Decimal:
        if raw_vote_weight < 0:
            return Decimal('0.0')
        return raw_vote_weight.sqrt()

    def get_voting_status(self, proposal_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        with get_session_scope(self.db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                return None
            
            total_actual_power_yes = session.query(func.sum(Vote.actual_vote_power)).filter_by(proposal_id=proposal_id, vote_choice='YES').scalar() or Decimal('0.0')
            total_actual_power_no = session.query(func.sum(Vote.actual_vote_power)).filter_by(proposal_id=proposal.id, vote_choice='NO').scalar() or Decimal('0.0')
            total_actual_power_abstain = session.query(func.sum(Vote.actual_vote_power)).filter_by(proposal_id=proposal.id, vote_choice='ABSTAIN').scalar() or Decimal('0.0')
            
            return {
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "title": proposal.title,
                "vote_start_time": proposal.vote_start_time.isoformat() if proposal.vote_start_time else None,
                "vote_end_time": proposal.vote_end_time.isoformat() if proposal.vote_end_time else None,
                "total_actual_power_yes": str(total_actual_power_yes),
                "total_actual_power_no": str(total_actual_power_no),
                "total_actual_power_abstain": str(total_actual_power_abstain),
                "required_quorum": str(proposal.required_quorum),
            }

    def get_total_vote_power_at_start_of_vote(self) -> Decimal:
        return Decimal('1000000.0') # Placeholder

    def queue_proposal_for_evaluation(self, proposal_id: uuid.UUID):
        logger.info(f"📨 Proposal ID {proposal_id} queued for evaluation.")
        pass


# ==============================================================================
# 3. Flask Blueprint for Reproductive System API
# ==============================================================================

reproductive_bp = Blueprint('reproductive', __name__, url_prefix='/api/v1/governance')


@reproductive_bp.route('/proposals', methods=['POST'])
@immune_system.check()
@validate_with(CreateProposalSchema)
def create_proposal() -> Tuple[Response, int]:
    proposal_data: CreateProposalSchema = g.validated_data
    logger.info(f"📥 API: Received proposal creation request for user: {proposal_data.proposer_user_id}")

    success, result = governance_service.create_new_proposal(proposal_data.model_dump())

    if success:
        return jsonify({
            "status": "success",
            "message": "Proposal created successfully.",
            "proposal_id": str(result['id']),
            "current_status": result['status']
        }), http.HTTPStatus.CREATED
    else:
        logger.warning(f"🚫 API: Proposal creation failed. Details: {result}")
        error_msg = result
        status_code = http.HTTPStatus.BAD_REQUEST
        if "Proposer user not found" in error_msg:
            status_code = http.HTTPStatus.NOT_FOUND
        elif "Database error" in error_msg:
            status_code = http.HTTPStatus.CONFLICT
        return jsonify({"status": "error", "error": error_msg}), status_code


@reproductive_bp.route('/proposals/<uuid:proposal_id>/vote', methods=['POST'])
@immune_system.check()
@validate_with(SubmitVoteSchema)
def submit_vote(proposal_id: uuid.UUID) -> Tuple[Response, int]:
    vote_data: SubmitVoteSchema = g.validated_data
    if vote_data.proposal_id != str(proposal_id):
        return jsonify({"status": "error", "error": "Mismatched proposal ID in URL and payload"}), http.HTTPStatus.BAD_REQUEST

    logger.info(f"📥 API: Received vote for proposal {proposal_id} from user {vote_data.voter_user_id}.")

    success, result = governance_service.submit_user_vote(proposal_id, vote_data.model_dump())

    if success:
        return jsonify({
            "status": "success",
            "message": "Vote submitted successfully.",
            "vote_id": str(result['id']),
            "proposal_id": str(result['proposal_id']),
            "actual_vote_power": str(result['actual_vote_power'])
        }), http.HTTPStatus.CREATED
    else:
        logger.warning(f"🚫 API: Vote submission failed. Details: {result}")
        error_msg = result
        status_code = http.HTTPStatus.BAD_REQUEST
        if "Proposal not found" in error_msg:
            status_code = http.HTTPStatus.NOT_FOUND
        elif "Proposal not open for voting" in error_msg or "Voting has ended" in error_msg or "Voting has not started" in error_msg:
            status_code = http.HTTPStatus.BAD_REQUEST
        elif "Insufficient balance" in error_msg:
            status_code = http.HTTPStatus.FORBIDDEN
        elif "Already voted" in error_msg or "Database error" in error_msg:
            status_code = http.HTTPStatus.CONFLICT
        return jsonify({"status": "error", "error": error_msg}), status_code


@reproductive_bp.route('/proposals', methods=['GET'])
@immune_system.check()
def list_proposals() -> Tuple[Response, int]:
    status_filter = request.args.get('status')
    user_id_filter = request.args.get('user_id')

    proposals = governance_service.get_all_proposals(status=status_filter, user_id=user_id_filter)

    return jsonify({
        "status": "success",
        "proposals": proposals
    }), http.HTTPStatus.OK


@reproductive_bp.route('/proposals/<uuid:proposal_id>', methods=['GET'])
@immune_system.check()
def get_proposal_details(proposal_id: uuid.UUID) -> Tuple[Response, int]:
    proposal_details = governance_service.get_proposal_by_id(proposal_id)
    if not proposal_details:
        return jsonify({"status": "error", "error": "Proposal not found"}), http.HTTPStatus.NOT_FOUND

    voting_status = reproductive_system.get_voting_status(proposal_id)

    if voting_status:
        proposal_details['voting_summary'] = voting_status

    return jsonify({"status": "success", "proposal": proposal_details}), http.HTTPStatus.OK


@reproductive_bp.route('/council_members', methods=['GET'])
@immune_system.check()
def list_council_members() -> Tuple[Response, int]:
    role_filter = request.args.get('role')

    members = governance_service.get_council_members(role=role_filter)

    return jsonify({
        "status": "success",
        "council_members": members
    }), http.HTTPStatus.OK


# Singleton instance to be imported/used elsewhere
reproductive_system = ReproductiveSystem()

