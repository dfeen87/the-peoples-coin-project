# peoples_coin/systems/status.py
from typing import Dict, Any, List
import datetime

# Import status functions from each system module
from peoples_coin.systems.metabolic_system import get_metabolic_status, get_metabolic_transaction_state
from peoples_coin.systems.cognitive_system import get_cognitive_status, get_cognitive_transaction_state
from peoples_coin.systems.nervous_system import get_nervous_status, get_nervous_transaction_state
from peoples_coin.systems.endocrine_system import get_endocrine_status
from peoples_coin.systems.immune_system import get_immune_status, get_immune_transaction_state
from peoples_coin.systems.skeleton_system import get_skeleton_info
from peoples_coin.systems.circulatory_system import get_circulatory_status
from peoples_coin.systems.reproductive_system import get_reproductive_status
# Removed unused import for get_overall_backend_status

# Optional controller import
try:
    from peoples_coin.systems.controller import get_controller_status
except ImportError:
    get_controller_status = None


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent backend events or logs."""
    now = datetime.datetime.utcnow()
    return [
        {
            "timestamp": (now - datetime.timedelta(minutes=i)).isoformat() + "Z",
            "event": f"Sample event {i}",
            "level": "info",
        }
        for i in range(limit)
    ]


def get_recent_goodwill_transactions(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent goodwill transactions from ledger or database."""
    now = datetime.datetime.utcnow()
    return [
        {
            "id": f"gw-txn-{i}",
            "timestamp": (now - datetime.timedelta(minutes=i * 2)).isoformat() + "Z",
            "initiator": f"user{i}",
        }
        for i in range(limit)
    ]


def determine_overall_txn_status(states: List[Dict[str, Any]]) -> str:
    """Aggregate individual system states into overall transaction status."""
    for state in states:
        s = state.get("state")
        if s in {"pending", "flagged", "review"}:
            return "pending_review"
        if s == "rejected":
            return "rejected"
    return "confirmed"


def get_goodwill_transaction_status_summary(limit: int = 20) -> Dict[str, Any]:
    """Provide a consolidated snapshot of recent goodwill transactions."""
    recent_txns = get_recent_goodwill_transactions(limit)

    txn_statuses = []
    for txn in recent_txns:
        txn_id = txn.get("id")

        metabolic_state = get_metabolic_transaction_state(txn_id)
        cognitive_state = get_cognitive_transaction_state(txn_id)
        nervous_state = get_nervous_transaction_state(txn_id)
        immune_state = get_immune_transaction_state(txn_id)

        overall_status = determine_overall_txn_status([
            metabolic_state,
            cognitive_state,
            nervous_state,
            immune_state,
        ])

        txn_statuses.append({
            "txnId": txn_id,
            "timestamp": txn.get("timestamp"),
            "initiator": txn.get("initiator"),
            "metabolic": metabolic_state,
            "cognitive": cognitive_state,
            "nervous": nervous_state,
            "immune": immune_state,
            "overallStatus": overall_status,
        })

    return {
        "count": len(txn_statuses),
        "transactions": txn_statuses,
    }


def get_backend_status() -> Dict[str, Any]:
    """Aggregate the health/status of all core systems."""
    status = {
        "metabolic": get_metabolic_status(),
        "cognitive": get_cognitive_status(),
        "nervous": get_nervous_status(),
        "endocrine": get_endocrine_status(),
        "immune": get_immune_status(),
        "skeleton": get_skeleton_info(),
        "circulatory": get_circulatory_status(),
        "reproductive": get_reproductive_status(),
        "controller": get_controller_status() if get_controller_status else None,
        "recentEvents": get_recent_events(),
        "goodwillTransactionSummary": get_goodwill_transaction_status_summary(),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    critical_systems = ["metabolic", "cognitive", "nervous", "immune"]
    status["systemHealthy"] = all(
        status.get(system, {}).get("healthy", False) for system in critical_systems
    )

    return status
