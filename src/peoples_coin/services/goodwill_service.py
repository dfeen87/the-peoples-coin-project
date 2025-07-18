import logging
from typing import Dict, Any, Tuple
from uuid import UUID

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction, UserAccount
from peoples_coin.validation.validate_transaction import validate_transaction, ValidationSuccess, ValidationFailure
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

class GoodwillService:
    def __init__(self):
        self.app = None
        self.db = None
        # Placeholder for your message queuing system (e.g., Pub/Sub client)
        self.message_queue_client = None # You'll initialize this in create_app()

    def init_app(self, app, db_instance, message_queue_client=None):
        self.app = app
        self.db = db_instance
        self.message_queue_client = message_queue_client
        logger.info("GoodwillService initialized.")

    def submit_and_queue_goodwill_action(self, data: Dict[str, Any]) -> Tuple[bool, Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Receives raw goodwill action data, validates it, persists to DB, and queues for blockchain minting.

        Args:
            data: The incoming dictionary of goodwill action data (conforming to TransactionModel).

        Returns:
            Tuple (success: bool, result: Dict/List[Dict] of data or errors).
        """
        logger.info("GoodwillService: Attempting to process goodwill submission.")

        # Step 1: Validate against TransactionModel schema and business rules
        validation_result: Union[ValidationSuccess, ValidationFailure] = validate_transaction(data)
        if not validation_result.is_valid:
            logger.warning(f"GoodwillService: Validation failed. Details: {validation_result.errors}")
            return False, validation_result.errors

        validated_goodwill_data = validation_result.data # This is the validated dict

        with get_session_scope(self.db) as session:
            try:
                # Find the UserAccount based on Firebase UID to link to internal ID
                user_account = session.query(UserAccount).filter_by(firebase_uid=validated_goodwill_data['user_id']).first()
                if not user_account:
                    logger.warning(f"GoodwillService: UserAccount not found for firebase_uid: {validated_goodwill_data['user_id']}")
                    return False, {"error": "User not found", "details": f"No UserAccount for Firebase UID {validated_goodwill_data['user_id']}"}

                # Create and persist the GoodwillAction
                goodwill_action = GoodwillAction(
                    performer_user_id=user_account.id, # Link to UserAccount's internal UUID PK
                    action_type=validated_goodwill_data['action_type'],
                    description=validated_goodwill_data['description'],
                    contextual_data=validated_goodwill_data.get('contextual_data', {}),
                    loves_value=validated_goodwill_data['loves_value'],
                    correlation_id=validated_goodwill_data.get('correlation_id'),
                    # Other optional fields can be mapped here
                    status='PENDING_VERIFICATION' # Initial status
                )
                session.add(goodwill_action)
                session.flush() # Flush to get the goodwill_action.id (UUID)

                logger.info(f"GoodwillService: GoodwillAction {goodwill_action.id} persisted. Now queuing for minting.")

                # Step 2: Queue for asynchronous blockchain minting
                # You need to implement your message queue client here (e.g., Pub/Sub)
                # This message should contain the goodwill_action.id (UUID)
                if self.message_queue_client:
                    # Example for Pub/Sub:
                    # topic_path = self.message_queue_client.publisher.topic_path(self.app.config['GCP_PROJECT_ID'], self.app.config['MINTING_TOPIC_ID'])
                    # self.message_queue_client.publisher.publish(topic_path, str(goodwill_action.id).encode('utf-8'))
                    logger.info(f"GoodwillService: Queued GoodwillAction ID {goodwill_action.id} for blockchain processing.")
                else:
                    logger.warning("GoodwillService: Message queue client not initialized. Action not queued for blockchain.")
                    # In production, this would be an error. For dev, might be acceptable.

                return True, {"action_id": str(goodwill_action.id), "status": "accepted"}

            except IntegrityError as e:
                logger.error(f"GoodwillService: Database integrity error: {e}", exc_info=True)
                return False, {"error": "Database error", "details": "Possible duplicate entry or constraint violation."}
            except Exception as e:
                logger.exception(f"GoodwillService: Unexpected error processing goodwill action.")
                return False, {"error": "Internal server error", "details": str(e)}

goodwill_service = GoodwillService()
