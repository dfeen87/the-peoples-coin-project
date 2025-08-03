import logging
from typing import Dict, Any
from sqlalchemy.exc import IntegrityError

from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.goodwill_action import GoodwillAction
from peoples_coin.validate.validate_transaction import validate_transaction
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

class GoodwillError(Exception):
    """Custom exception raised for goodwill service related issues."""
    pass

class GoodwillService:
    def __init__(self):
        self.app = None
        self.db = None
        self.message_queue_client = None  # e.g., Pub/Sub client instance

    def init_app(self, app, db_instance, message_queue_client=None):
        self.app = app
        self.db = db_instance
        self.message_queue_client = message_queue_client
        logger.info("GoodwillService initialized.")

    def submit_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates goodwill action data, persists it, and queues it for blockchain minting.

        Args:
            data: Incoming goodwill action data dict.

        Returns:
            Dict with action_id and status on success.

        Raises:
            GoodwillError on validation or processing errors.
        """
        logger.info("GoodwillService: Processing goodwill submission.")

        # Validate incoming data
        validation_result = validate_transaction(data)
        if not validation_result.is_valid:
            logger.warning(f"Validation failed: {validation_result.errors}")
            raise GoodwillError(f"Validation failed: {validation_result.errors}")

        validated_data = validation_result.data

        with get_session_scope(self.db) as session:
            try:
                # Link Firebase UID to internal UserAccount UUID
                user_account = session.query(UserAccount).filter_by(firebase_uid=validated_data['user_id']).first()
                if not user_account:
                    logger.warning(f"UserAccount not found for Firebase UID: {validated_data['user_id']}")
                    raise GoodwillError(f"No UserAccount found for Firebase UID {validated_data['user_id']}")

                goodwill_action = GoodwillAction(
                    performer_user_id=user_account.id,
                    action_type=validated_data['action_type'],
                    description=validated_data['description'],
                    contextual_data=validated_data.get('contextual_data', {}),
                    loves_value=validated_data['loves_value'],
                    correlation_id=validated_data.get('correlation_id'),  # Optional
                    status='PENDING_VERIFICATION',
                )
                session.add(goodwill_action)
                session.flush()  # Assign ID

                logger.info(f"GoodwillAction {goodwill_action.id} persisted. Queueing for blockchain minting.")

                if self.message_queue_client:
                    # Example placeholder for queuing logic:
                    # topic_path = self.message_queue_client.publisher.topic_path(
                    #     self.app.config['GCP_PROJECT_ID'],
                    #     self.app.config['MINTING_TOPIC_ID']
                    # )
                    # self.message_queue_client.publisher.publish(topic_path, str(goodwill_action.id).encode('utf-8'))
                    logger.info(f"Queued GoodwillAction ID {goodwill_action.id} for blockchain processing.")
                else:
                    logger.warning("Message queue client not initialized; skipping queuing.")

                return {"action_id": str(goodwill_action.id), "status": "accepted"}

            except IntegrityError as e:
                logger.error("Database integrity error during goodwill action processing.", exc_info=True)
                raise GoodwillError("Database error: possible duplicate or constraint violation.") from e
            except Exception as e:
                logger.exception("Unexpected error processing goodwill action.")
                raise GoodwillError(f"Internal server error: {str(e)}") from e


goodwill_service = GoodwillService()

