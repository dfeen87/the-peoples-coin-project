# peoples_coin/systems/reproductive_system.py
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any

from flask import Flask
from peoples_coin.extensions import db
from peoples_coin.models.db_utils import get_session_scope
# CORRECTED: Import from the central models package
from peoples_coin.models import Proposal, Vote

logger = logging.getLogger(__name__)

class ReproductiveSystem:
    """Manages core governance logic and calculations."""
    def __init__(self):
        self.app: Optional[Flask] = None
        self.db = None
        self._initialized = False
        logger.info("🌱 ReproductiveSystem instance created.")

    def init_app(self, app: Flask, db_instance):
        if self._initialized:
            return
        self.app = app
        self.db = db_instance
        self._initialized = True
        logger.info("🌱 ReproductiveSystem initialized.")

    def calculate_quadratic_vote_power(self, raw_vote_weight: Decimal) -> Decimal:
        """Calculates vote power using quadratic voting logic."""
        if raw_vote_weight < 0:
            return Decimal('0.0')
        return raw_vote_weight.sqrt()

    def get_voting_status(self, proposal_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieves current voting status for a proposal."""
        with get_session_scope(self.db) as session:
            proposal = session.query(Proposal).filter_by(id=proposal_id).first()
            if not proposal:
                return None
            
            # NOTE: The 'actual_vote_power' column is not in the final Vote model.
            # This logic will need to be updated in your service layer to calculate
            # power based on the user's balance at the time of the vote.
            # For now, we can count the votes.
            yes_votes = session.query(Vote).filter_by(proposal_id=proposal_id, vote_value='FOR').count()
            no_votes = session.query(Vote).filter_by(proposal_id=proposal_id, vote_value='AGAINST').count()

            return {
                "proposal_id": str(proposal.id),
                "status": proposal.status,
                "yes_votes": yes_votes,
                "no_votes": no_votes,
            }

# Singleton instance
reproductive_system = ReproductiveSystem()

# --- Function for status page ---
def get_reproductive_status():
    """Health check for the Reproductive System."""
    if reproductive_system._initialized:
        return {"active": True, "healthy": True, "info": "Reproductive System operational"}
    else:
        return {"active": False, "healthy": False, "info": "Reproductive System not initialized"}
