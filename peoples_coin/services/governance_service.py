import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from decimal import Decimal, getcontext, InvalidOperation
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import func

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import Proposal, Vote, UserAccount, CouncilMember
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

# Set a safe precision for Decimal operations (adjust as needed)
getcontext().prec = 28

STATUS_PROPOSAL_DRAFT = 'DRAFT'
STATUS_PROPOSAL_VOTING = 'VOTING'
STATUS_PROPOSAL_PASSED = 'PASSED'
STATUS_PROPOSAL_FAILED = 'FAILED'
STATUS_PROPOSAL_EXECUTED = 'EXECUTED'

VOTE_CHOICE_YES = 'YES'
VOTE_CHOICE_NO = 'NO'
VOTE_CHOICE_ABSTAIN = 'ABSTAIN'
VALID_VOTE_CHOICES = {VOTE_CHOICE_YES, VOTE_CHOICE_NO, VOTE_CHOICE_ABSTAIN}


class ProposalError(Exception):
    """Custom exception for proposal and voting errors."""


class GovernanceService:
    def __init__(self):
        self.app = None
        self.db = None
        logger.info("GovernanceService initialized.")

    def init_app(self, app, db_instance):
        self.app = app
        self.db = db_instance

    # ------------------------- Proposal lifecycle -------------------------
    def create_new_proposal(self, proposer_user_id: UUID, proposal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates and saves a new proposal to the database, raising an exception on failure.

        Expects proposal_data to contain at least: title, description, proposal_type.
        Optional: details (dict), vote_duration_days (int), required_quorum (float between 0 and 1).
        """
        with get_session_scope(self.db) as session:
            try:
                # All logic is now wrapped in a single try block
                user_account = session.query(UserAccount).filter_by(id=proposer_user_id).one()
                
                vote_start = None
                vote_end = None
                if proposal_data.get('vote_duration_days'):
                    vote_start = datetime.now(timezone.utc)
                    vote_end = vote_start + timedelta(days=int(proposal_data['vote_duration_days']))

                # Validate quorum: must be fraction between 0 and 1
                required_quorum_raw = Decimal(str(proposal_data.get('required_quorum', '0')))
                if required_quorum_raw < 0 or required_quorum_raw > 1:
                    raise ProposalError('required_quorum must be a decimal between 0 and 1 (e.g. 0.25 for 25%).')

                new_proposal = Proposal(
                    proposer_user_id=user_account.id,
                    title=proposal_data['title'],
                    description=proposal_data['description'],
                    proposal_type=proposal_data['proposal_type'],
                    details=proposal_data.get('details', {}),
                    status=STATUS_PROPOSAL_DRAFT,
                    vote_start_time=vote_start,
                    vote_end_time=vote_end,
                    required_quorum=required_quorum_raw
                )
                session.add(new_proposal)
                session.flush()

                return new_proposal.to_dict()

            except NoResultFound:
                session.rollback()
                raise ProposalError("Proposer user not found.")
            except IntegrityError:
                session.rollback()
                logger.error("Proposal creation failed: Integrity error.", exc_info=True)
                raise ProposalError("Proposal with similar details might already exist.")
            except ProposalError:
                session.rollback()
                raise
            except Exception as e:
                session.rollback()
                logger.exception("Unexpected error creating proposal.")
                raise ProposalError(f"Internal error: {e}")

    def open_voting(self, proposal_id: UUID, duration_days: Optional[int] = None) -> Dict[str, Any]:
        """Move a proposal from DRAFT to VOTING. Optionally set/override vote duration in days."""
        with get_session_scope(self.db) as session:
            try:
                proposal = session.query(Proposal).filter_by(id=proposal_id).one()
            except NoResultFound:
                raise ProposalError("Proposal not found.")

            if proposal.status != STATUS_PROPOSAL_DRAFT:
                raise ProposalError("Proposal is not in DRAFT status and cannot be opened for voting.")

            now = datetime.now(timezone.utc)
            proposal.vote_start_time = now
            if duration_days is not None:
                proposal.vote_end_time = now + timedelta(days=int(duration_days))
            elif not proposal.vote_end_time:
                # default to 7 days if nothing provided
                proposal.vote_end_time = now + timedelta(days=7)

            proposal.status = STATUS_PROPOSAL_VOTING
            session.add(proposal)
            session.flush()
            return proposal.to_dict()

    def close_voting(self, proposal_id: UUID) -> Dict[str, Any]:
        """Force close voting early and evaluate results immediately."""
        with get_session_scope(self.db) as session:
            try:
                proposal = session.query(Proposal).filter_by(id=proposal_id).one()
            except NoResultFound:
                raise ProposalError("Proposal not found.")

            if proposal.status != STATUS_PROPOSAL_VOTING:
                raise ProposalError("Proposal is not open for voting.")

            # set vote end to now so evaluation can proceed
            proposal.vote_end_time = datetime.now(timezone.utc)
            session.add(proposal)
            session.flush()

        # perform evaluation outside the nested session block so evaluate_proposal_results
        # obtains its own session and commits cleanly.
        return self.evaluate_proposal_results(proposal_id)

    # ------------------------- Voting -------------------------
    def submit_user_vote(self, proposal_id: UUID, voter_user_id: UUID, vote_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and records a user's vote, raising an exception on failure."""
        with get_session_scope(self.db) as session:
            try:
                # All logic is now wrapped in one try block for clarity
                proposal = session.query(Proposal).filter_by(id=proposal_id).one()
                voter_account = session.query(UserAccount).filter_by(id=voter_user_id).one()

                if proposal.status != STATUS_PROPOSAL_VOTING:
                    raise ProposalError("Proposal not open for voting.")

                now = datetime.now(timezone.utc)
                if proposal.vote_start_time and now < proposal.vote_start_time:
                    raise ProposalError("Voting has not started yet.")
                if proposal.vote_end_time and now > proposal.vote_end_time:
                    raise ProposalError("Voting has ended.")

                try:
                    raw_vote_weight = Decimal(str(vote_data['vote_weight']))
                except (KeyError, InvalidOperation):
                    raise ProposalError("Invalid or missing vote_weight.")

                if raw_vote_weight <= 0:
                    raise ProposalError("Vote weight must be positive.")

                try:
                    voter_balance = Decimal(str(voter_account.balance))
                except Exception:
                    raise ProposalError("Voter account balance is invalid or not set.")

                if voter_balance < raw_vote_weight:
                    raise ProposalError("Insufficient balance for vote.")

                existing_vote = session.query(Vote).filter_by(proposal_id=proposal.id, voter_user_id=voter_account.id).first()
                if existing_vote:
                    raise ProposalError("Already voted on this proposal.")

                vote_choice = vote_data.get('vote_choice')
                if vote_choice not in VALID_VOTE_CHOICES:
                    raise ProposalError(f"Invalid vote_choice. Must be one of: {', '.join(VALID_VOTE_CHOICES)}")

                try:
                    actual_vote_power = raw_vote_weight.sqrt()
                except Exception as e:
                    logger.exception("Error computing sqrt for quadratic voting.")
                    raise ProposalError(f"Invalid vote weight for quadratic calculation: {e}")
                
                new_vote = Vote(
                    proposal_id=proposal.id,
                    voter_user_id=voter_account.id,
                    vote_value=vote_choice,
                    rationale=vote_data.get('rationale', None),
                    vote_weight=raw_vote_weight,
                    actual_vote_power=actual_vote_power
                )

                session.add(new_vote)
                session.flush()

                return new_vote.to_dict()

            except NoResultFound as e:
                # Catch specific ORM errors here
                session.rollback()
                raise ProposalError(f"Database lookup failed: {e}")
            except IntegrityError:
                # Catch this specific error for race conditions
                session.rollback()
                logger.exception("Integrity error saving vote.")
                raise ProposalError("Failed to save vote; it may already exist.")
            except ProposalError:
                # Re-raise our own custom errors
                session.rollback()
                raise
            except Exception as e:
                # Catch all other unexpected errors
                session.rollback()
                logger.exception("Unexpected error submitting vote.")
                raise ProposalError(f"Internal error: {e}")

    # ------------------------- Queries -------------------------
    def get_all_proposals(self, status: Optional[str] = None, user_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        """Fetches all proposals, optionally filtering by status and user ID (UUID)."""
        with get_session_scope(self.db) as session:
            query = session.query(Proposal).order_by(Proposal.created_at.desc())
            if status:
                query = query.filter_by(status=status.upper())
            if user_id:
                query = query.filter_by(proposer_user_id=user_id)
            
            proposals = query.all()
            return [p.to_dict() for p in proposals]

    def get_proposal_by_id(self, proposal_id: UUID) -> Optional[Dict[str, Any]]:
        """Fetches a single proposal by its ID."""
        with get_session_scope(self.db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            return proposal.to_dict() if proposal else None

    def get_council_members(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches all council members, optionally filtering by role."""
        with get_session_scope(self.db) as session:
            query = session.query(CouncilMember)
            if role:
                query = query.filter(func.lower(CouncilMember.role) == role.lower())
            members = query.all()
            return [m.to_dict() for m in members]

    # ------------------------- Evaluation -------------------------
    def evaluate_proposal_results(self, proposal_id: UUID) -> Tuple[bool, str]:
        logger.info(f"Evaluating results for Proposal ID {proposal_id}.")
        with get_session_scope(self.db) as session:
            try:
                proposal = session.query(Proposal).filter_by(id=proposal_id).one()
            except NoResultFound:
                return False, "Proposal not found."

            now = datetime.now(timezone.utc)
            if proposal.status != STATUS_PROPOSAL_VOTING:
                return False, "Proposal is not in voting status."
            if proposal.vote_end_time and now < proposal.vote_end_time:
                return False, "Voting period has not ended."

            # Sum actual vote power per choice; coalesce to Decimal('0.0')
            total_yes = session.query(func.coalesce(func.sum(Vote.actual_vote_power), Decimal('0.0'))).filter_by(
                proposal_id=proposal.id, vote_value=VOTE_CHOICE_YES).scalar() or Decimal('0.0')
            total_no = session.query(func.coalesce(func.sum(Vote.actual_vote_power), Decimal('0.0'))).filter_by(
                proposal_id=proposal.id, vote_value=VOTE_CHOICE_NO).scalar() or Decimal('0.0')
            total_abstain = session.query(func.coalesce(func.sum(Vote.actual_vote_power), Decimal('0.0'))).filter_by(
                proposal_id=proposal.id, vote_value=VOTE_CHOICE_ABSTAIN).scalar() or Decimal('0.0')

            total_votes = total_yes + total_no + total_abstain

            total_eligible_power = self.get_total_vote_power_at_start_of_vote()

            quorum_threshold = (proposal.required_quorum * total_eligible_power)

            if total_votes < quorum_threshold:
                proposal.status = STATUS_PROPOSAL_FAILED
                session.add(proposal)
                logger.info(f"Proposal {proposal_id} failed: quorum not met.")
                return False, "Quorum not met."

            if total_yes > total_no:
                proposal.status = STATUS_PROPOSAL_PASSED
                session.add(proposal)
                logger.info(f"Proposal {proposal_id} passed.")
                return True, "Proposal passed."
            else:
                proposal.status = STATUS_PROPOSAL_FAILED
                session.add(proposal)
                logger.info(f"Proposal {proposal_id} failed by vote.")
                return False, "Proposal failed by vote."

    def get_total_vote_power_at_start_of_vote(self) -> Decimal:
        """Placeholder: implement real snapshot logic as needed.

        This function should be replaced with a snapshot that calculates the total eligible
        voting power at the start of the proposal. By default it returns a large constant
        to keep older behavior.
        """
        return Decimal('1000000.0')


# Singleton instance
governance_service = GovernanceService()
