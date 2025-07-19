import logging
from typing import Dict, Any, Tuple, Union, List
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount
from peoples_coin.validation.validate_transaction import validate_transaction, ValidationSuccess, ValidationFailure
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

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

    def submit_and_queue_goodwill_action(
        self, data: Dict[str, Any]
    ) -> Tuple[bool, Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Validates goodwill action data, persists it, and queues it for blockchain minting.

        Args:
            data: Incoming goodwill action data dict.

        Returns:
            Tuple: (success flag, dict of action_id/status or list of validation errors)
        """
        logger.info("GoodwillService: Processing goodwill submission.")

        # Validate incoming data
        validation_result = validate_transaction(data)
        if not validation_result.is_valid:
            logger.warning(f"Validation failed: {validation_result.errors}")
            return False, validation_result.errors

        validated_data = validation_result.data

        with get_session_scope(self.db) as session:
            try:
                # Link Firebase UID to internal UserAccount UUID
                user_account = session.query(UserAccount).filter_by(firebase_uid=validated_data['user_id']).first()
                if not user_account:
                    logger.warning(f"UserAccount not found for Firebase UID: {validatedated_data['user_id']}")
                    return False, {"error": "User not found", "details": f"No UserAccount for Firebase UID {validated_data['user_id']}"}

                goodwill_action = GoodwillAction(
                    performer_user_id=user_account.id,
                    action_type=validated_data['action_type'],
                    description=validated_data['description'],
                    contextual_data=validated_data.get('contextual_data', {}),
                    loves_value=validated_data['loves_value'],
                    correlation_id=validated_data.get('correlation_id'),
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

                return True, {"action_id": str(goodwill_action.id), "status": "accepted"}

            except IntegrityError as e:
                logger.error("Database integrity error during goodwill action processing.", exc_info=True)
                return False, {"error": "Database error", "details": "Possible duplicate or constraint violation."}
            except Exception as e:
                logger.exception("Unexpected error processing goodwill action.")
                return False, {"error": "Internal server error", "details": str(e)}

goodwill_service = GoodwillService()

