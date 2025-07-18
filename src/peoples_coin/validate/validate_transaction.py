from typing import Union, Dict, Any, List, Optional
from pydantic import BaseModel, ValidationError, Field, constr
from typing_extensions import Literal
from uuid import UUID
from datetime import datetime, timezone, timedelta
import logging
import re
import json

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature
from base64 import b64decode

logger = logging.getLogger(__name__)


# ==============================================================================
# Configuration / Whitelist
# ==============================================================================

# Note: This is a placeholder. In a real app, ALLOWED_CONTRIBUTORS would
# likely be dynamically fetched or managed via a more secure system,
# potentially linking to actual user IDs or verified public addresses.
ALLOWED_CONTRIBUTORS = {"user1_firebase_uid", "user2_firebase_uid", "admin_firebase_uid", "service-account_uid"}

KEY_REGEX = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")  # alphanumeric + dash, max 64 chars
MAX_TIMESTAMP_SKEW_SECONDS = 300  # 5 minutes skew allowed


# ==============================================================================
# 1. Define the Core Data Schema (Updated to align with GoodwillActionSchema)
# ==============================================================================

class TransactionModel(BaseModel):
    # constr(regex=...) is deprecated in Pydantic v2. Use constr(pattern=...)
    # This model now mirrors the GoodwillActionSchema for submitted data
    user_id: str = Field(..., description="Firebase UID of the user performing the action") # Corresponds to GoodwillActionSchema.user_id
    action_type: str = Field(..., description="Type of goodwill action (e.g., 'Community Contribution')")
    description: str = Field(..., description="Description of the goodwill action")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of the action")
    loves_value: int = Field(..., ge=1, le=100, description="Value of goodwill action (1-100 loves)") # NEW: Added loves_value
    contextual_data: Dict[str, Any] = Field(default_factory=dict, description="Additional context as JSON")
    correlation_id: Optional[str] = Field(None, description="Optional ID for correlating events")
    # Crypto fields for verification - these are for the incoming payload's integrity
    signature: str = Field(None, description="Base64-encoded digital signature of the payload")
    public_key_pem: str = Field(None, description="Contributor's public key in PEM format")
    
    # These fields from old TransactionModel are removed as they don't directly map to current GoodwillActionSchema
    # key: constr(pattern=KEY_REGEX.pattern) = Field(..., description="Transaction key or identifier") # Replaced by action_type
    # value: Any = Field(..., description="Value associated with the transaction") # Replaced by loves_value, description, contextual_data
    # contributor: str = Field(..., description="User or entity contributing the transaction") # Replaced by user_id

# ==============================================================================
# 2. Define Explicit Return Models for Validation Results
# ==============================================================================

class ValidationSuccess(BaseModel):
    is_valid: Literal[True] = True
    data: Dict[str, Any]


class ValidationFailure(BaseModel):
    is_valid: Literal[False] = False
    errors: List[Dict[str, Any]]


# ==============================================================================
# 3. Helper: Signature Verification
# ==============================================================================

def verify_signature(public_key_pem: str, signature_b64: str, payload: dict) -> bool:
    """
    Verifies an ECDSA signature (secp256k1) over the JSON payload.
    """
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        signature = b64decode(signature_b64)
        message = json.dumps(payload, sort_keys=True).encode()

        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, Exception) as e:
        logger.warning(f"Invalid signature: {e}")
        return False


def is_timestamp_valid(timestamp: datetime) -> bool:
    """
    Ensures the timestamp is not too far in the past or future.
    """
    now = datetime.now(timezone.utc)
    delta = abs((now - timestamp).total_seconds())
    return delta <= MAX_TIMESTAMP_SKEW_SECONDS


# ==============================================================================
# 4. Validation Function
# ==============================================================================

def validate_transaction(data: dict) -> Union[ValidationSuccess, ValidationFailure]:
    """
    Validates the transaction data against schema and business rules.
    This function expects data conforming to the TransactionModel schema.
    """
    try:
        # Pydantic schema validation (TransactionModel now updated)
        validated = TransactionModel(**data)

        # Check contributor whitelist (using user_id from new schema)
        if validated.user_id not in ALLOWED_CONTRIBUTORS:
            error = {
                "loc": ["user_id"],
                "msg": f"User ID '{validated.user_id}' is not an allowed contributor.",
                "type": "value_error.user_not_allowed"
            }
            logger.warning(f"❌ User ID not allowed: {validated.user_id}")
            return ValidationFailure(errors=[error])

        # Check timestamp skew
        if not is_timestamp_valid(validated.timestamp):
            error = {
                "loc": ["timestamp"],
                "msg": f"Timestamp skew exceeds {MAX_TIMESTAMP_SKEW_SECONDS} seconds.",
                "type": "value_error.timestamp_skew"
            }
            logger.warning(f"❌ Timestamp invalid: {validated.timestamp}")
            return ValidationFailure(errors=[error])

        # Optional: verify signature if present
        if validated.signature and validated.public_key_pem:
            # Reconstruct payload for signature verification
            # Ensure this payload matches EXACTLY what was signed on the client-side
            payload_for_signature = {
                "user_id": validated.user_id,
                "action_type": validated.action_type,
                "description": validated.description,
                "timestamp": validated.timestamp.isoformat(),
                "loves_value": validated.loves_value,
                "contextual_data": validated.contextual_data # Include all fields that were signed
            }
            # Only include correlation_id if it's present and was part of the original signed payload
            if validated.correlation_id:
                payload_for_signature["correlation_id"] = validated.correlation_id

            if not verify_signature(validated.public_key_pem, validated.signature, payload_for_signature):
                error = {
                    "loc": ["signature"],
                    "msg": "Invalid cryptographic signature.",
                    "type": "value_error.invalid_signature"
                }
                logger.warning("❌ Invalid signature.")
                return ValidationFailure(errors=[error])

        # No longer checking if value is JSON-serializable if it's explicitly typed fields like loves_value
        # If contextual_data can contain non-serializable objects, you might add a check here.

        logger.info("✅ Transaction validated successfully.")
        return ValidationSuccess(data=validated.model_dump())

    except ValidationError as e:
        logger.warning(f"❌ Pydantic validation failed: {e.errors()}")
        return ValidationFailure(errors=e.errors())

    except Exception as e:
        logger.exception(f"💥 Unexpected error during transaction validation.")
        return ValidationFailure(errors=[{"loc": ["_general"], "msg": str(e), "type": "internal_error"}])


# ==============================================================================
# Example Usage: (These are comments for how to use the function)
# ==============================================================================
#
# from flask import request, jsonify, Blueprint
#
# some_bp = Blueprint('some_api', __name__)
#
# @some_bp.route('/example_submit', methods=['POST'])
# def example_submit_endpoint():
#     incoming_data = request.get_json()
#     result = validate_transaction(incoming_data)
#
#     if result.is_valid:
#         validated_data = result.data
#         # Now you can use validated_data to persist to DB, queue for blockchain, etc.
#         return jsonify({"message": "Success!", "data": validated_data}), 200
#     else:
#         return jsonify({"error": "Validation failed", "details": result.errors}), 400
