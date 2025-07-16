from typing import Union, Dict, Any, List
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

ALLOWED_CONTRIBUTORS = {"user1", "user2", "admin", "service-account"}

KEY_REGEX = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")  # alphanumeric + dash, max 64 chars
MAX_TIMESTAMP_SKEW_SECONDS = 300  # 5 minutes skew allowed


# ==============================================================================
# 1. Define the Core Data Schema
# ==============================================================================

class TransactionModel(BaseModel):
    # Change constr(regex=...) to constr(pattern=...) for Pydantic v2 compatibility
    key: constr(pattern=KEY_REGEX.pattern) = Field(..., description="Transaction key or identifier")
    value: Any = Field(..., description="Value associated with the transaction")
    contributor: str = Field(..., description="User or entity contributing the transaction")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp")
    signature: str = Field(None, description="Base64-encoded digital signature")
    public_key_pem: str = Field(None, description="Contributor's public key in PEM format")


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
    """
    try:
        validated = TransactionModel(**data)

        # Check contributor whitelist
        if validated.contributor not in ALLOWED_CONTRIBUTORS:
            error = {
                "loc": ["contributor"],
                "msg": f"Contributor '{validated.contributor}' is not allowed.",
                "type": "value_error.contributor_not_allowed"
            }
            logger.warning(f"❌ Contributor not allowed: {validated.contributor}")
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
            payload = {
                "key": validated.key,
                "value": validated.value,
                "contributor": validated.contributor,
                "timestamp": validated.timestamp.isoformat()
            }
            if not verify_signature(validated.public_key_pem, validated.signature, payload):
                error = {
                    "loc": ["signature"],
                    "msg": "Invalid cryptographic signature.",
                    "type": "value_error.invalid_signature"
                }
                logger.warning("❌ Invalid signature.")
                return ValidationFailure(errors=[error])

        # Optional: ensure value is JSON-serializable
        try:
            json.dumps(validated.value)
        except Exception:
            error = {
                "loc": ["value"],
                "msg": "Value is not JSON-serializable.",
                "type": "value_error.value_not_serializable"
            }
            logger.warning("❌ Value is not JSON-serializable.")
            return ValidationFailure(errors=[error])

        logger.info("✅ Transaction validated successfully.")
        return ValidationSuccess(data=validated.model_dump())

    except ValidationError as e:
        logger.warning(f"❌ Validation failed: {e.errors()}")
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
#         validated_data = result.data
#         return jsonify({"message": "Success!", "data": validated_data}), 200
#     else:
#         return jsonify({"error": "Validation failed", "details": result.errors}), 400

