# peoples_coin/systems/metabolic_system.py

import datetime
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory simulation store for metabolic transaction states
_transaction_states: Dict[str, Dict[str, object]] = {}


def get_metabolic_status() -> Dict[str, object]:
    """
    Returns health status of the Metabolic system.
    Replace stub logic with real health checks, e.g. DB, API status, metrics.
    """
    try:
        # Here you could check DB connections, caches, external dependencies, etc.
        status = {
            "healthy": True,
            "message": "Metabolic system operational",
            "lastChecked": datetime.datetime.utcnow().isoformat() + "Z",
        }
        logger.debug(f"Metabolic status: {status}")
        return status
    except Exception as e:
        logger.error(f"Error fetching metabolic status: {e}", exc_info=True)
        return {
            "healthy": False,
            "message": f"Error fetching metabolic status: {e}",
            "lastChecked": datetime.datetime.utcnow().isoformat() + "Z",
        }


def get_metabolic_transaction_state(transaction_id: str) -> Dict[str, object]:
    """
    Retrieve state info for a metabolic transaction.
    Stub uses in-memory dictionary; replace with DB/cache lookup in prod.
    """
    try:
        txn = _transaction_states.get(transaction_id)
        if txn:
            logger.debug(f"Found metabolic transaction state: {txn}")
            return txn
        else:
            # Default state if not found
            default_state = {
                "transactionId": transaction_id,
                "state": "pending",
                "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            }
            logger.debug(f"Returning default metabolic transaction state: {default_state}")
            return default_state
    except Exception as e:
        logger.error(f"Error getting metabolic transaction state for {transaction_id}: {e}", exc_info=True)
        return {
            "transactionId": transaction_id,
            "state": "unknown",
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
            "error": str(e),
        }


def update_metabolic_transaction_state(transaction_id: str, new_state: str) -> None:
    """
    Update the transaction state.
    Stub for demo/testing. Persist to DB or message queue in real use.
    """
    try:
        _transaction_states[transaction_id] = {
            "transactionId": transaction_id,
            "state": new_state,
            "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        }
        logger.info(f"Metabolic transaction {transaction_id} updated to state '{new_state}'")
    except Exception as e:
        logger.error(f"Failed to update metabolic transaction {transaction_id}: {e}", exc_info=True)


def clear_all_transaction_states() -> None:
    """
    Helper function to clear all in-memory transaction states.
    Useful for tests or restarting simulated state.
    """
    _transaction_states.clear()
    logger.info("All metabolic transaction states cleared.")


if __name__ == "__main__":
    # Simple test run when executing this module directly
    logging.basicConfig(level=logging.DEBUG)

    print("Initial metabolic status:")
    print(get_metabolic_status())

    test_txn_id = "txn123"
    print(f"\nGetting state for transaction {test_txn_id} (should be default 'pending'):")
    print(get_metabolic_transaction_state(test_txn_id))

    print(f"\nUpdating state for transaction {test_txn_id} to 'confirmed':")
    update_metabolic_transaction_state(test_txn_id, "confirmed")

    print(f"\nGetting updated state for transaction {test_txn_id}:")
    print(get_metabolic_transaction_state(test_txn_id))

    print("\nClearing all transaction states:")
    clear_all_transaction_states()
    print(get_metabolic_transaction_state(test_txn_id))

