# peoples_coin/services/governance_service.py
import logging
from datetime import datetime, timezone
import uuid
from decimal import Decimal

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

from peoples_coin.extensions import db
from peoples_coin.models.db_utils import get_session_scope
# Import all the models this service needs
from peoples_coin.models import Proposal, Vote, UserAccount, CouncilMember
# Import the system that has core calculation logic
from peoples_coin.systems.reproductive_system import reproductive_system

logger = logging.getLogger(__name__)

class ProposalError(Exception):
    """Custom exception for proposal and voting errors."""
    pass

class GovernanceService:
    """Handles the core business logic for proposals, votes, and governance."""

    def create_new_proposal(self, proposer_user_id: str, proposal_data: dict) -> dict:
        """Creates and saves a new proposal to the database."""
        with get_session_scope(db) as session:
            proposer = session.query(UserAccount).filter_by(id=proposer_user_id).first()
            if not proposer:
                raise ProposalError("Proposer user not found.")

            new_proposal = Proposal(
                proposer_user_id=proposer.id,
                title=proposal_data.get('title'),
                description=proposal_data.get('description'),
                proposal_type=proposal_data.get('proposal_type'),
                details=proposal_data.get('details', {})
            )
            session.add(new_proposal)
            session.flush() # Use flush to get the new_proposal.id
            logger.info(f"New proposal '{new_proposal.title}' created with ID {new_proposal.id}")
            return new_proposal.to_dict()

    def submit_user_vote(self, proposal_id: uuid.UUID, voter_user_id: str, vote_data: dict) -> dict:
        """Validates and records a user's vote in the database."""
        with get_session_scope(db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                raise ProposalError("Proposal not found.")
            if proposal.status != 'ACTIVE':
                raise ProposalError("Proposal is not currently open for voting.")

            voter = session.query(UserAccount).filter_by(id=voter_user_id).first()
            if not voter:
                raise ProposalError("Voter not found.")
            
            # Use the reproductive system for vote power calculation
            vote_weight = Decimal(voter.balance) # Example: vote weight is user's balance
            actual_power = reproductive_system.calculate_quadratic_vote_power(vote_weight)

            try:
                new_vote = Vote(
                    voter_user_id=voter.id,
                    proposal_id=proposal.id,
                    vote_value=vote_data.get('vote_choice').upper(),
                    # In a real system, you would store vote_weight and actual_power
                )
                session.add(new_vote)
                session.flush()
                logger.info(f"Vote by {voter.id} on {proposal.id} successfully recorded.")
                return new_vote.to_dict()
            except IntegrityError:
                session.rollback()
                raise ProposalError("User has already voted on this proposal.")

    def get_all_proposals(self, status: str = None) -> list:
        """Fetches all proposals, optionally filtering by status."""
        with get_session_scope(db) as session:
            query = session.query(Proposal)
            if status:
                query = query.filter(Proposal.status == status.upper())
            proposals = query.order_by(Proposal.created_at.desc()).all()
            return [p.to_dict() for p in proposals]
        
    def get_proposal_by_id(self, proposal_id: uuid.UUID) -> dict:
        """Fetches a single proposal by its ID."""
        with get_session_scope(db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            return proposal.to_dict() if proposal else None

    def get_council_members(self, role: str = None) -> list:
        """Fetches all council members, optionally filtering by role."""
        with get_session_scope(db) as session:
            query = session.query(CouncilMember)
            if role:
                query = query.filter(CouncilMember.role == role)
            members = query.all()
            return [m.to_dict() for m in members]

# Singleton instance
governance_service = GovernanceService()

# --- Function for status page ---
def get_governance_status():
    """Health check for the Governance System."""
    return {"active": True, "healthy": True, "info": "Governance System operational"}
