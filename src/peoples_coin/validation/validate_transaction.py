# peoples_coin/peoples_coin/validation/validate_transaction.py

from typing import Tuple, Dict, Any
from pydantic import BaseModel, ValidationError, Field

class TransactionModel(BaseModel):
    key: str = Field(..., description="Transaction key or identifier")
    value: Any = Field(..., description="Value associated with the transaction")
    contributor: str = Field(..., description="User or entity contributing the transaction")

def validate_transaction(data: dict) -> Tuple[bool, Dict]:
    """
    Validates the transaction data against the TransactionModel schema.

    Args:
        data (dict): Incoming transaction data.

    Returns:
        Tuple[bool, dict]: (is_valid, validated_data or error details)
    """
    try:
        transaction = TransactionModel(**data)
        # If valid, return True and the dict version of validated data
        return True, transaction.dict()
    except ValidationError as e:
        # Return False and validation errors in dict form
        return False, e.errors()

