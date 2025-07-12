"""
validation.py
Provides data validation utilities for The People’s Coin skeleton system using Pydantic.
"""

from pydantic import BaseModel, ValidationError, Field, Extra, validator
from typing import List, Tuple, Union
import time
import logging

# Configurable max allowed future drift
MAX_FUTURE_DRIFT_SECONDS = 60

logger = logging.getLogger(__name__)


class Contribution(BaseModel):
    """
    Represents a validated act of kindness or transaction.
    """
    contributor: str = Field(..., min_length=1, description="Contributor name must not be empty")
    tags: List[str] = Field(..., min_items=1, description="At least one tag is required")
    value: float = Field(..., gt=0, le=1000, description="Value must be > 0 and ≤ 1000")
    timestamp: float = Field(..., ge=0, description="A valid UNIX timestamp.")

    @validator('timestamp')
    def timestamp_must_not_be_in_the_future(cls, v: float) -> float:
        """
        Validates that the timestamp is not further in the future than the allowed drift.
        This validator runs at the time of validation, not at definition time.
        """
        allowed_future_time = time.time() + MAX_FUTURE_DRIFT_SECONDS
        if v > allowed_future_time:
            raise ValueError(f"Timestamp is too far in the future")
        return v

    class Config:
        # Enforce strict schema (no extra fields allowed) by default
        extra = Extra.forbid


def _format_error(e: ValidationError) -> str:
    """Returns a JSON string from a Pydantic ValidationError."""
    return e.json(indent=2)


def validate_transaction(
    data: dict,
    log_errors: bool = True,
    strict: bool = True
) -> Tuple[bool, Union[Contribution, str]]:
    """
    Validates incoming transaction data against the Contribution schema.

    Returns:
        A tuple of (bool, result). If valid, result is a Contribution object.
        If invalid, result is a JSON string of the errors.
    """
    schema = Contribution
    if not strict:
        # Create a temporary relaxed version of the schema if not strict
        class ContributionRelaxed(Contribution):
            class Config:
                extra = Extra.allow
        schema = ContributionRelaxed

    try:
        contribution = schema(**data)
        return True, contribution
    except ValidationError as e:
        error_details = _format_error(e)
        if log_errors:
            logger.warning(f"Validation failed for transaction: {error_details}")
        return False, error_details


def validate_transactions(
    transactions: List[dict],
    log_errors: bool = True,
    strict: bool = True
) -> Tuple[bool, List[Contribution], List[str]]:
    """

    Validates a list of transactions, separating valid and invalid results.

    Returns:
        A tuple of (all_valid_bool, list_of_valid_contributions, list_of_errors).
    """
    valid_contributions = []
    errors = []

    for i, tx in enumerate(transactions):
        is_valid, result = validate_transaction(tx, log_errors=log_errors, strict=strict)
        if is_valid:
            valid_contributions.append(result)
        else:
            errors.append(f"Transaction index {i}: {result}")

    all_are_valid = not errors
    return all_are_valid, valid_contributions, errors
