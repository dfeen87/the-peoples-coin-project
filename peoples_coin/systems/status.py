# system/status.py

from typing import Dict, Any, List
import datetime

# Import your biological systems
from system.metabolic import get_metabolic_status, get_metabolic_transaction_state
from system.cognitive import get_cognitive_status, get_cognitive_transaction_state
from system.nervous import get_nervous_status, get_nervous_transaction_state
from system.endocrine import get_endocrine_status
from system.immune import get_immune_status, get_immune_transaction_state
from system.skeleton import get_skeleton_info
from system.circulatory import get_circulatory_status
from system.reproductive import get_reproductive_status
from system.backend_status_service import get_overall_backend_status


def get_backend_status(transaction_id):
    return get_overall_backend_status(transaction_id)

def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieve recent backend events or logs.
    Replace this stub with your real logging or nervous system event fetching.
    """
    now = datetime.datetime.utcnow()
    events = [
        {
            "timestamp": (now - datetime.timedelta(minutes=i)).isoformat() + "Z",
            "event": f"Sample event {i}",
            "level": "info",
        }
        for i in range(limit)
    ]
    return events


def get_recent_goodwill_transactions(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch recent goodwill transactions from your ledger or database.
    Replace this stub with a real DB or cache call.
    Each transaction dict must include at least: id, timestamp, initiator.
    """
    now = datetime.datetime.utcnow()
    return [
        {"id": f"gw-txn-{i}", "timestamp": (now - datetime.timedelta(minutes=i * 2)).isoformat() + "Z", "initiator": f"user{i}"}
        for i in range(limit)
    ]


def determine_overall_txn_status(states: List[Dict[str, Any]]) -> str:
    """
    Aggregate individual system states into an overall transaction status.
    For example, if any system flags 'pending', 'flagged', or 'review', overall is 'pending_review'.
    If any system rejects, overall is 'rejected'.
    Otherwise, 'confirmed'.
    """
    for state in states:
        s = state.get("state")
        if s in ["pending", "flagged", "review"]:
            return "pending_review"
        if s == "rejected":
            return "rejected"
    return "confirmed"


def get_goodwill_transaction_status_summary(limit: int = 20) -> Dict[str, Any]:
    """
    Provide a consolidated snapshot of recent goodwill transactions and their
    processing states across key systems.
    """
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
    """
    Aggregate the status of all core biological systems, goodwill transaction
    processing status, and metadata.
    Returns a dict suitable for JSON serialization.
    """

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
        "nodeVersion": get_skeleton_info().get("version", "unknown"),
        "recentEvents": get_recent_events(),
        "goodwillTransactionSummary": get_goodwill_transaction_status_summary(),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    # Overall system health flag based on critical systems' health
    critical_systems = ["metabolic", "cognitive", "nervous", "endocrine", "immune", "circulatory", "reproductive"]
    status["systemHealthy"] = all(
        status.get(system, {}).get("healthy", True) for system in critical_systems
    )

    return status

# Temporary stubs — replace with real implementations in your biological system modules

def get_metabolic_status():
    return {"active": True, "healthy": True, "info": "Metabolic system operational"}

def get_metabolic_transaction_state(txn_id):
    return {"state": "minted", "confirmed": True}

def get_cognitive_status():
    return {"active": True, "healthy": True, "info": "Cognitive system operational"}

def get_cognitive_transaction_state(txn_id):
    return {"state": "governance-approved", "confirmed": True}

def get_nervous_status():
    return {"active": True, "healthy": True, "info": "Nervous system operational"}

def get_nervous_transaction_state(txn_id):
    return {"state": "broadcasted", "confirmed": True}

def get_immune_status():
    return {"active": True, "healthy": True, "info": "Immune system operational"}

def get_immune_transaction_state(txn_id):
    return {"state": "clear", "confirmed": True}

def get_endocrine_status():
    return {"active": True, "healthy": True, "info": "Endocrine system operational"}

def get_skeleton_info():
    return {"version": "1.0.0", "schema": "v1"}

def get_circulatory_status():
    return {"active": True, "healthy": True, "info": "Circulatory system operational"}

def get_reproductive_status():
    return {"active": True, "healthy": True, "info": "Reproductive system operational"}

try:
    from system.controller import get_controller_status
except ImportError:
    get_controller_status = None

if __name__ == "__main__":
    import json
    print(json.dumps(get_backend_status(), indent=2))

