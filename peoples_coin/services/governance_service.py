import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.models import Proposal, Vote, UserAccount, CouncilMember
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

STATUS_PROPOSAL_DRAFT = 'DRAFT'
STATUS_PROPOSAL_VOTING = 'VOTING'
STATUS_PROPOSAL_PASSED = 'PASSED'
STATUS_PROPOSAL_FAILED = 'FAILED'
STATUS_PROPOSAL_EXECUTED = 'EXECUTED'

VOTE_CHOICE_YES = 'YES'
VOTE_CHOICE_NO = 'NO'
VOTE_CHOICE_ABSTAIN = 'ABSTAIN'


class GovernanceService:
    def __init__(self):
        self.app = None
        self.db = None
        logger.info("GovernanceService initialized.")

    def init_app(self, app, db_instance):
        self.app = app
        self.db = db_instance

    def create_new_proposal(self, proposal_data: Dict[str, Any]) -> Tuple[bool, Union[Dict[str, Any], str]]:
        with get_session_scope(self.db) as session:
            try:
                user_account = session.query(UserAccount).filter_by(firebase_uid=proposal_data['proposer_user_id']).first()
                if not user_account:
                    return False, "Proposer user not found."

                vote_start = datetime.now(timezone.utc)
                vote_end = None
                if proposal_data.get('vote_duration_days'):
                    vote_end = vote_start + timedelta(days=int(proposal_data['vote_duration_days']))

                new_proposal = Proposal(
                    proposer_user_id=user_account.id,
                    title=proposal_data['title'],
                    description=proposal_data['description'],
                    proposal_type=proposal_data['proposal_type'],
                    details=proposal_data.get('details', {}),
                    status=STATUS_PROPOSAL_DRAFT,
                    vote_start_time=vote_start,
                    vote_end_time=vote_end,
                    required_quorum=Decimal(str(proposal_data.get('required_quorum', 0.0)))
                )
                session.add(new_proposal)
                session.flush()

                return True, new_proposal.to_dict()

            except IntegrityError:
                logger.error("Proposal creation failed: Integrity error.", exc_info=True)
                return False, "Proposal with similar details might already exist."
            except Exception as e:
                logger.exception("Unexpected error creating proposal.")
                return False, f"Internal error: {e}"

    def submit_user_vote(self, proposal_id: UUID, vote_data: Dict[str, Any]) -> Tuple[bool, Union[Dict[str, Any], str]]:
        with get_session_scope(self.db) as session:
            try:
                proposal = session.query(Proposal).filter_by(id=proposal_id).first()
                if not proposal:
                    return False, "Proposal not found."
                if proposal.status != STATUS_PROPOSAL_VOTING:
                    return False, "Proposal not open for voting."

                now = datetime.now(timezone.utc)
                if proposal.vote_start_time and now < proposal.vote_start_time:
                    return False, "Voting has not started yet."
                if proposal.vote_end_time and now > proposal.vote_end_time:
                    return False, "Voting has ended."

                voter_account = session.query(UserAccount).filter_by(firebase_uid=vote_data['voter_user_id']).first()
                if not voter_account:
                    return False, "Voter user not found."

                raw_vote_weight = Decimal(str(vote_data['vote_weight']))
                if raw_vote_weight <= 0:
                    return False, "Vote weight must be positive."
                if voter_account.balance < raw_vote_weight:
                    return False, "Insufficient balance for vote."

                existing_vote = session.query(Vote).filter_by(proposal_id=proposal.id, voter_user_id=voter_account.id).first()
                if existing_vote:
                    return False, "Already voted on this proposal."

                actual_vote_power = raw_vote_weight.sqrt()

                new_vote = Vote(
                    proposal_id=proposal.id,
                    voter_user_id=voter_account.id,
                    vote_value=vote_data['vote_choice'],
                    rationale=vote_data.get('rationale', None),
                    vote_weight=raw_vote_weight,
                    actual_vote_power=actual_vote_power
                )

                session.add(new_vote)

                voter_account.balance -= raw_vote_weight
                session.add(voter_account)

                session.flush()

                return True, new_vote.to_dict()

            except Exception as e:
                logger.exception("Unexpected error submitting vote.")
                return False, f"Internal error: {e}"

    def get_all_proposals(self, status: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with get_session_scope(self.db) as session:
            query = session.query(Proposal).order_by(Proposal.created_at.desc())
            if status:
                query = query.filter_by(status=status.upper())
            if user_id:
                user_account = session.query(UserAccount).filter_by(firebase_uid=user_id).first()
                if user_account:
                    query = query.filter_by(proposer_user_id=user_account.id)
                else:
                    return []
            return [p.to_dict() for p in query.all()]

    def get_proposal_by_id(self, proposal_id: UUID) -> Optional[Dict[str, Any]]:
        with get_session_scope(self.db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            return proposal.to_dict() if proposal else None

    def get_council_members(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        with get_session_scope(self.db) as session:
            query = session.query(CouncilMember)
            if role:
                query = query.filter(func.lower(CouncilMember.role) == role.lower())
            return [m.to_dict() for m in query.all()]

    def evaluate_proposal_results(self, proposal_id: UUID) -> Tuple[bool, str]:
        logger.info(f"Evaluating results for Proposal ID {proposal_id}.")
        with get_session_scope(self.db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                return False, "Proposal not found."

            now = datetime.now(timezone.utc)
            if proposal.status != STATUS_PROPOSAL_VOTING:
                return False, "Proposal is not in voting status."
            if proposal.vote_end_time and now < proposal.vote_end_time:
                return False, "Voting period has not ended."

            total_yes = session.query(func.coalesce(func.sum(Vote.actual_vote_power), 0)).filter_by(
                proposal_id=proposal.id, vote_value=VOTE_CHOICE_YES).scalar()
            total_no = session.query(func.coalesce(func.sum(Vote.actual_vote_power), 0)).filter_by(
                proposal_id=proposal.id, vote_value=VOTE_CHOICE_NO).scalar()
            total_abstain = session.query(func.coalesce(func.sum(Vote.actual_vote_power), 0)).filter_by(
                proposal_id=proposal.id, vote_value=VOTE_CHOICE_ABSTAIN).scalar()

            total_votes = total_yes + total_no + total_abstain

            quorum_threshold = proposal.required_quorum * self.get_total_vote_power_at_start_of_vote()

            if total_votes < quorum_threshold:
                proposal.status = STATUS_PROPOSAL_FAILED
                session.add(proposal)
                logger.info(f"Proposal {proposal_id} failed: quorum not met.")
                return False, "Quorum not met."

            if total_yes > total_no:
                proposal.status = STATUS_PROPOSAL_PASSED
                session.add(proposal)
                logger.info(f"Proposal {proposal_id} passed.")
                # TODO: Add execution trigger here
                return True, "Proposal passed."
            else:
                proposal.status = STATUS_PROPOSAL_FAILED
                session.add(proposal)
                logger.info(f"Proposal {proposal_id} failed by vote.")
                return False, "Proposal failed by vote."

    def get_total_vote_power_at_start_of_vote(self) -> Decimal:
        # Placeholder: implement real snapshot logic as needed
        return Decimal('1000000.0')

governance_service = GovernanceService()

