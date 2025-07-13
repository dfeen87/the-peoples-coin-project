from typing import Tuple, Dict, Any, Union, List

from pydantic import BaseModel, ValidationError, Field

# ==============================================================================
# 1. Define the Core Data Schema
# ==============================================================================

class TransactionModel(BaseModel):
    """Defines the structure for an incoming transaction."""
    key: str = Field(..., description="Transaction key or identifier")
    # Using Union can make the model more specific if you know the possible types.
    # 'Any' is also a valid choice if the value can truly be anything.
    value: Union[str, int, float, dict, list] = Field(..., description="Value associated with the transaction")
    contributor: str = Field(..., description="User or entity contributing the transaction")


# ==============================================================================
# 2. Define Explicit Return Models for Validation Results
# ==============================================================================

class ValidationSuccess(BaseModel):
    """
    Represents a successful validation result.
    The 'is_valid' flag is a literal True, making the result type-safe.
    """
    is_valid: bool = Field(True, Literal=True)
    data: TransactionModel


class ValidationFailure(BaseModel):
    """
    Represents a failed validation result.
    Contains a list of detailed Pydantic errors.
    """
    is_valid: bool = Field(False, Literal=False)
    errors: List[Dict[str, Any]]


# ==============================================================================
# 3. Implement the Validation Function
# ==============================================================================

def validate_transaction(data: dict) -> Union[ValidationSuccess, ValidationFailure]:
    """
    Validates the transaction data against the TransactionModel schema.

    This function is type-safe and returns an unambiguous result, making it
    easy for the caller to handle both success and failure cases.

    Args:
        data (dict): Incoming transaction data.

    Returns:
        Union[ValidationSuccess, ValidationFailure]: An object indicating
        whether the validation passed or failed, containing either the
        validated data or a list of errors.
    """
    try:
        # Attempt to parse and validate the data using the core model.
        validated_transaction = TransactionModel(**data)
        
        # On success, wrap the validated data in a ValidationSuccess object.
        return ValidationSuccess(data=validated_transaction)
        
    except ValidationError as e:
        # On failure, wrap the Pydantic errors in a ValidationFailure object.
        return ValidationFailure(errors=e.errors())

# ==============================================================================
# Example Usage:
# ==============================================================================
#
# def some_api_endpoint():
#     incoming_data = request.get_json()
#     result = validate_transaction(incoming_data)
#
#     if result.is_valid:
#         # You can now safely access result.data, and your IDE knows its type.
#         validated_data = result.data.model_dump() # Use .dict() for Pydantic v1
#         # ... process the valid data ...
#         return jsonify({"message": "Success!", "data": validated_data}), 200
#     else:
#         # You can safely access result.errors.
#         return jsonify({"error": "Validation failed", "details": result.errors}), 400
#

