# peoples_coin/systems/backend_status_service.py

# --- CORRECTED: Use relative imports from within your project package ---

# Metabolic system
try:
    from peoples_coin.systems.metabolic_system import get_metabolic_status, get_metabolic_transaction_state
except ImportError:
    def get_metabolic_status(): return {"active": False, "info": "Metabolic system not available"}
    def get_metabolic_transaction_state(txn_id): return {"state": "unknown"}

# Cognitive system
try:
    from peoples_coin.systems.cognitive_system import get_cognitive_status, get_cognitive_transaction_state
except ImportError:
    def get_cognitive_status(): return {"active": False, "info": "Cognitive system not available"}
    def get_cognitive_transaction_state(txn_id): return {"state": "unknown"}

# Nervous system
try:
    from peoples_coin.systems.nervous_system import get_nervous_status, get_nervous_transaction_state
except ImportError:
    def get_nervous_status(): return {"active": False, "info": "Nervous system not available"}
    def get_nervous_transaction_state(txn_id): return {"state": "unknown"}

# Immune system
try:
    from peoples_coin.systems.immune_system import get_immune_status, get_immune_transaction_state
except ImportError:
    def get_immune_status(): return {"active": False, "info": "Immune system not available"}
    def get_immune_transaction_state(txn_id): return {"state": "unknown"}

# Endocrine system
try:
    from peoples_coin.systems.endocrine_system import get_endocrine_status
except ImportError:
    def get_endocrine_status(): return {"active": False, "info": "Endocrine system not available"}

# Skeleton system
try:
    from peoples_coin.systems.skeleton_system import get_skeleton_info
except ImportError:
    def get_skeleton_info(): return {"version": "unknown", "schema": "unknown"}

# Circulatory system
try:
    from peoples_coin.systems.circulatory_system import get_circulatory_status
except ImportError:
    def get_circulatory_status(): return {"active": False, "info": "Circulatory system not available"}

# Reproductive system
try:
    from peoples_coin.systems.reproductive_system import get_reproductive_status
except ImportError:
    def get_reproductive_status(): return {"active": False, "info": "Reproductive system not available"}

# Controller system (optional)
try:
    from peoples_coin.systems.controller import get_controller_status
except ImportError:
    def get_controller_status(): return {"active": False, "info": "Controller system not available"}


def get_overall_backend_status(txn_id=None):
    """
    Returns the aggregated backend status of all systems.
    Optionally, provide txn_id to get transaction states.
    """
    status = {
        "metabolic": get_metabolic_status(),
        "cognitive": get_cognitive_status(),
        "nervous": get_nervous_status(),
        "immune": get_immune_status(),
        "endocrine": get_endocrine_status(),
        "skeleton": get_skeleton_info(),
        "circulatory": get_circulatory_status(),
        "reproductive": get_reproductive_status(),
        "controller": get_controller_status(),
        "transaction_state": {
            "metabolic": get_metabolic_transaction_state(txn_id) if txn_id else None,
            "cognitive": get_cognitive_transaction_state(txn_id) if txn_id else None,
            "nervous": get_nervous_transaction_state(txn_id) if txn_id else None,
            "immune": get_immune_transaction_state(txn_id) if txn_id else None,
        },
    }
    return status
