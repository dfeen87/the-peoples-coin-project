# peoples_coin/peoples_coin/validation/validate_transaction.py

def validate_transaction(data: dict) -> tuple[bool, dict]:
    """
    Placeholder for transaction validation logic.
    Replace with actual validation later.
    """
    # For now, just assume it's valid if it's a dict
    if isinstance(data, dict):
        # Example: check for 'key', 'value', 'contributor'
        if all(k in data for k in ['key', 'value', 'contributor']):
            return True, data # Return True and the data itself as the 'result'
        else:
            return False, {"reason": "Missing required fields (key, value, contributor)"}
    return False, {"reason": "Invalid data format, expected a dictionary"}
