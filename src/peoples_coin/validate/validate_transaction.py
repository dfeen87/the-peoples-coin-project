from typing import Union, Dict, Any, List, Optional
from pydantic import BaseModel, ValidationError, Field
from typing_extensions import Literal
from uuid import UUID, uuid4
from datetime import datetime, timezone
import logging
import json
import re

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature
from base64 import b64decode

logger = logging.getLogger(__name__)

# ==============================================================================
# Configuration / Whitelist
# ==============================================================================

def load_allowed_contributors() -> set[str]:
    """
    Stub: load the allowed contributors dynamically, e.g., from DB or config.
    Replace this with actual implementation.
    """
    return {"user1_firebase_uid", "user2_firebase_uid", "admin_firebase_uid", "service-account_uid"}

ALLOWED_CONTRIBUTORS = load_allowed_contributors()

MAX_TIMESTAMP_SKEW_SECONDS = 300  # 5 minutes skew allowed

# ==============================================================================
# Data Schemas
# ==============================================================================

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

# ==============================================================================
# Helpers
# ==============================================================================

def extract_signed_payload(validated: TransactionModel) -> dict:
    """
    Build the exact payload that was signed on client.
    """
    payload = {
        "user_id": validated.user_id,
        "action_type": validated.action_type,
        "description": validated.description,
        "timestamp": validated.timestamp.isoformat(),
        "loves_value": validated.loves_value,
        "contextual_data": validated.contextual_data
    }
    if validated.correlation_id:
        payload["correlation_id"] = validated.correlation_id
    return payload

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
# Main Validation Logic
# ==============================================================================

def validate_transaction(data: dict) -> Union[ValidationSuccess, ValidationFailure]:
    """
    Validates the transaction data against schema and business rules.
    """
    try:
        validated = TransactionModel.model_validate(data)
        request_id = validated.correlation_id or str(uuid4())

        # Check whitelist
        if validated.user_id not in ALLOWED_CONTRIBUTORS:
            error = {
                "loc": ["user_id"],
                "msg": f"User ID '{validated.user_id}' is not an allowed contributor.",
                "type": "value_error.user_not_allowed"
            }
            logger.warning(f"[{request_id}] ❌ User not allowed: {validated.user_id}")
            return ValidationFailure(is_valid=False, errors=[error])

        # Check timestamp skew
        if not is_timestamp_valid(validated.timestamp):
            error = {
                "loc": ["timestamp"],
                "msg": f"Timestamp skew exceeds {MAX_TIMESTAMP_SKEW_SECONDS} seconds.",
                "type": "value_error.timestamp_skew"
            }
            logger.warning(f"[{request_id}] ❌ Invalid timestamp: {validated.timestamp}")
            return ValidationFailure(is_valid=False, errors=[error])

        # Verify signature if present
        if validated.signature and validated.public_key_pem:
            payload_for_signature = extract_signed_payload(validated)
            if not verify_signature(validated.public_key_pem, validated.signature, payload_for_signature):
                error = {
                    "loc": ["signature"],
                    "msg": "Invalid cryptographic signature.",
                    "type": "value_error.invalid_signature"
                }
                logger.warning(f"[{request_id}] ❌ Invalid signature.")
                return ValidationFailure(is_valid=False, errors=[error])

        logger.info(f"[{request_id}] ✅ Transaction validated: user_id={validated.user_id}")
        return ValidationSuccess(is_valid=True, data=validated.model_dump())

    except ValidationError as e:
        logger.warning(f"❌ Pydantic validation failed: {e.errors()}")
        return ValidationFailure(is_valid=False, errors=e.errors())

    except Exception as e:
        logger.exception(f"💥 Unexpected error during validation.")
        return ValidationFailure(is_valid=False, errors=[{
            "loc": ["_general"], "msg": str(e), "type": "internal_error"
        }])

