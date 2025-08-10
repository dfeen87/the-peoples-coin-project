# system/backend_status_service.py

# Metabolic system
try:
    from system.metabolic import get_metabolic_status, get_metabolic_transaction_state
except ImportError:
    def get_metabolic_status():
        return {"active": False, "info": "Metabolic system not available"}

    def get_metabolic_transaction_state(txn_id):
        return {"state": "unknown"}

# Cognitive system
try:
    from system.cognitive import get_cognitive_status, get_cognitive_transaction_state
except ImportError:
    def get_cognitive_status():
        return {"active": False, "info": "Cognitive system not available"}

    def get_cognitive_transaction_state(txn_id):
        return {"state": "unknown"}

# Nervous system
try:
    from system.nervous import get_nervous_status, get_nervous_transaction_state
except ImportError:
    def get_nervous_status():
        return {"active": False, "info": "Nervous system not available"}

    def get_nervous_transaction_state(txn_id):
        return {"state": "unknown"}

# Immune system
try:
    from system.immune import get_immune_status, get_immune_transaction_state
except ImportError:
    def get_immune_status():
        return {"active": False, "info": "Immune system not available"}

    def get_immune_transaction_state(txn_id):
        return {"state": "unknown"}

# Endocrine system (AILEE)
try:
    from system.endocrine import get_endocrine_status
except ImportError:
    def get_endocrine_status():
        return {"active": False, "info": "Endocrine system not available"}

# Skeleton system
try:
    from system.skeleton import get_skeleton_info
except ImportError:
    def get_skeleton_info():
        return {"version": "unknown", "schema": "unknown"}

# Circulatory system
try:
    from system.circulatory import get_circulatory_status
except ImportError:
    def get_circulatory_status():
        return {"active": False, "info": "Circulatory system not available"}

# Reproductive system
try:
    from system.reproductive import get_reproductive_status
except ImportError:
    def get_reproductive_status():
        return {"active": False, "info": "Reproductive system not available"}

# Controller system (optional)
try:
    from system.controller import get_controller_status
except ImportError:
    def get_controller_status():
        return {"active": False, "info": "Controller system not available"}


def get_overall_backend_status(txn_id=None):
    """
    Returns the aggregated backend status of all biological systems.
    Optionally, provide txn_id to get transaction states where applicable.
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
            # Add other systems with transaction state if available
        },
    }
    return status

