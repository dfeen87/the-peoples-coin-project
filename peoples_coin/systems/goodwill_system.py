# peoples_coin/systems/goodwill_system.py
import logging
from typing import Dict, Any

from peoples_coin.extensions import db
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import GoodwillAction, UserAccount

logger = logging.getLogger(__name__)

class GoodwillError(Exception):
    """Custom exception for goodwill service errors."""
    pass

class GoodwillSystem:
    """Handles the core business logic for processing goodwill actions."""

    def submit_and_queue_goodwill_action(self, action_data: dict) -> Dict[str, Any]:
        """Validates and saves a new goodwill action, queuing it for processing."""
        user_id = action_data.get("user_id")
        if not user_id:
            raise GoodwillError("Missing user_id in action data.")

        with get_session_scope(db) as session:
            user = session.query(UserAccount).filter_by(id=user_id).first()
            if not user:
                raise GoodwillError(f"User with id {user_id} not found.")

            new_action = GoodwillAction(
                performer_user_id=user.id,
                action_type=action_data.get("action_type", "general"),
                description=action_data.get("description", "No description provided."),
                # Add any other fields from action_data to the model
            )
            session.add(new_action)
            session.flush() # Flush to get the new_action.id
            
            action_id = str(new_action.id)
            logger.info(f"Goodwill action {action_id} created for user {user_id} and queued.")

            # In a real system, you would add this action_id to a background job queue (e.g., Celery)
            # For now, we'll just return the ID.

            return {"action_id": action_id}
            
    def get_action_status(self, user_id: str, action_id: str) -> str:
        """Returns the status of a specific goodwill action for a user."""
        with get_session_scope(db) as session:
            action = session.query(GoodwillAction).filter_by(id=action_id, performer_user_id=user_id).first()
            return action.status if action else None

    # ... [other methods like get_user_summary, get_user_history would go here] ...

# Singleton instance
goodwill_system = GoodwillSystem()

# --- Function for status page ---
def get_goodwill_status():
    """Returns the current operational status of the goodwill system."""
    return {"active": True, "healthy": True, "info": "Goodwill system operational"}
