# src/peoples_coin/validate/transaction_validator.py (example new name)

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Union, Dict, Any, List, Optional, Callable, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Literal
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
from base64 import b64decode

logger = logging.getLogger(__name__)

# --- Configuration ---
MAX_TIMESTAMP_SKEW_SECONDS = 300  # 5 minutes

# --- Pydantic Schemas ---
class TransactionModel(BaseModel):
    user_id: str
    action_type: str
    description: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    loves_value: int = Field(..., ge=1, le=100)
    contextual_data: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    signature: Optional[str] = None
    public_key_pem: Optional[str] = None

class ValidationSuccess(BaseModel):
    is_valid: Literal[True] = True
    data: Dict[str, Any]

class ValidationFailure(BaseModel):
    is_valid: Literal[False] = False
    errors: List[Dict[str, Any]]

# --- Helper Functions ---
def _is_signature_required(action_type: str) -> bool:
    """Determines if a signature is mandatory based on the action type."""
    # Example: High-value actions must be signed.
    high_value_actions = {"treasury_spend", "protocol_change"}
    return action_type in high_value_actions

def _verify_signature(public_key_pem: str, signature_b64: str, payload: dict) -> bool:
    """Verifies an ECDSA signature over a JSON payload."""
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        signature = b64decode(signature_b64)
        message = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError) as e:
        logger.warning(f"Signature verification failed: {e}")
        return False

def _is_timestamp_valid(timestamp: datetime) -> bool:
    """Ensures the timestamp is within an acceptable skew of the current time."""
    now = datetime.now(timezone.utc)
    delta = abs((now - timestamp).total_seconds())
    return delta <= MAX_TIMESTAMP_SKEW_SECONDS

def _extract_signed_payload(validated: TransactionModel) -> dict:
    """Constructs the exact payload that was signed on the client."""
    # This must perfectly match the client-side signing implementation.
    payload = {
        "user_id": validated.user_id,
        "action_type": validated.action_type,
        "description": validated.description,
        "timestamp": validated.timestamp.isoformat().replace('+00:00', 'Z'),
        "loves_value": validated.loves_value,
        "contextual_data": validated.contextual_data
    }
    if validated.correlation_id:
        payload["correlation_id"] = validated.correlation_id
    return payload

# --- Main Validation Logic ---
def validate_transaction(
    data: dict,
    authenticated_user_id: str,
    allowed_contributors_loader: Callable[[], Set[str]]
) -> Union[ValidationSuccess, ValidationFailure]:
    """
    Validates transaction data against schema and business rules, including authentication checks.

    Args:
        data: The raw transaction data from the request.
        authenticated_user_id: The user ID from a trusted auth token (e.g., Firebase UID).
        allowed_contributors_loader: A function that returns the current set of allowed contributors.
    """
    try:
        validated = TransactionModel.model_validate(data)
        errors = []

        # 1. Authentication Check: Does the payload user match the token user?
        if validated.user_id != authenticated_user_id:
            errors.append({"loc": ["user_id"], "msg": "Payload user ID does not match authenticated user."})

        # 2. Authorization Check: Is the user on the whitelist?
        if validated.user_id not in allowed_contributors_loader():
            errors.append({"loc": ["user_id"], "msg": f"User '{validated.user_id}' is not an allowed contributor."})

        # 3. Timestamp Skew Check
        if not _is_timestamp_valid(validated.timestamp):
            errors.append({"loc": ["timestamp"], "msg": f"Timestamp skew exceeds {MAX_TIMESTAMP_SKEW_SECONDS} seconds."})

        # 4. Signature Check
        if _is_signature_required(validated.action_type):
            if not validated.signature or not validated.public_key_pem:
                errors.append({"loc": ["signature"], "msg": "A cryptographic signature is required for this action type."})
            else:
                payload_to_verify = _extract_signed_payload(validated)
                if not _verify_signature(validated.public_key_pem, validated.signature, payload_to_verify):
                    errors.append({"loc": ["signature"], "msg": "Invalid cryptographic signature."})
        
        if errors:
            logger.warning(f"Transaction validation failed for user {validated.user_id}: {errors}")
            return ValidationFailure(is_valid=False, errors=errors)

        logger.info(f"✅ Transaction validated for user: {validated.user_id}")
        return ValidationSuccess(is_valid=True, data=validated.model_dump())

    except ValidationError as e:
        logger.warning(f"Pydantic validation failed: {e.errors()}")
        return ValidationFailure(is_valid=False, errors=e.errors())
    except Exception as e:
        logger.exception("💥 Unexpected error during transaction validation.")
        return ValidationFailure(is_valid=False, errors=[{"loc": ["_general"], "msg": str(e), "type": "internal_error"}])
