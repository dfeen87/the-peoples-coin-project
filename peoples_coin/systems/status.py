# peoples_coin/systems/status.py
from typing import Dict, Any, List
import datetime

# --- Corrected and Consolidated Imports ---
from peoples_coin.systems.metabolic_system import get_metabolic_status, get_metabolic_transaction_state
from peoples_coin.systems.cognitive_system import get_cognitive_status, get_cognitive_transaction_state
from peoples_coin.systems.nervous_system import get_nervous_status, get_nervous_transaction_state
from peoples_coin.systems.endocrine_system import get_endocrine_status
from peoples_coin.systems.immune_system import get_immune_status, get_immune_transaction_state
from peoples_coin.systems.circulatory_system import get_circulatory_status
from peoples_coin.systems.reproductive_system import get_reproductive_status

# Optional controller import
try:
    from peoples_coin.systems.controller import get_controller_status
except ImportError:
    get_controller_status = None


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent backend events (placeholder)."""
    now = datetime.datetime.utcnow()
    return [
        {
            "timestamp": (now - datetime.timedelta(minutes=i)).isoformat() + "Z",
            "event": f"Sample event {i}",
            "level": "info",
        }
        for i in range(limit)
    ]


def get_goodwill_transaction_status_summary(limit: int = 20) -> Dict[str, Any]:
    """Provide a snapshot of recent goodwill transaction statuses (placeholder)."""
    now = datetime.datetime.utcnow()
    recent_txns = [
        {"id": f"gw-txn-{i}", "timestamp": (now - datetime.timedelta(minutes=i*2)).isoformat() + "Z", "initiator": f"user{i}"}
        for i in range(limit)
    ]

    txn_statuses = []
    for txn in recent_txns:
        txn_id = txn.get("id")
        # In a real system, you'd fetch real states. Here we use placeholders.
        states = [
            get_metabolic_transaction_state(txn_id),
            get_cognitive_transaction_state(txn_id),
            get_nervous_transaction_state(txn_id),
            get_immune_transaction_state(txn_id),
        ]
        # This aggregation logic is a good pattern
        overall_status = "confirmed"
        for state in states:
            s = state.get("state")
            if s in {"pending", "review"}:
                overall_status = "pending_review"
                break
            if s == "rejected":
                overall_status = "rejected"
                break
        
        txn_statuses.append({
            "txnId": txn_id,
            "timestamp": txn.get("timestamp"),
            "overallStatus": overall_status
        })

    return {"count": len(txn_statuses), "transactions": txn_statuses}


def get_backend_status() -> Dict[str, Any]:
    """Aggregate the health status of all core systems."""
    status = {
        "metabolic": get_metabolic_status(),
        "cognitive": get_cognitive_status(),
        "nervous": get_nervous_status(),
        "endocrine": get_endocrine_status(),
        "immune": get_immune_status(),
        "circulatory": get_circulatory_status(),
        "reproductive": get_reproductive_status(),
        "controller": get_controller_status() if get_controller_status else {"active": False, "info": "Not available"},
        "goodwillTransactionSummary": get_goodwill_transaction_status_summary(),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    critical_systems = ["metabolic", "cognitive", "nervous", "immune"]
    status["systemHealthy"] = all(
        status.get(system, {}).get("healthy", False) for system in critical_systems
    )

    return status
