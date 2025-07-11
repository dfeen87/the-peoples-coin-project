"""
validation.py
Provides data validation utilities for The People’s Coin skeleton system.
"""

from pydantic import BaseModel, ValidationError, Field, Extra
from typing import List, Tuple, Union, Optional
import time
import json
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
    timestamp: float = Field(
        ...,
        ge=0,
        le=time.time() + MAX_FUTURE_DRIFT_SECONDS,
        description=f"Valid UNIX timestamp (≤ now + {MAX_FUTURE_DRIFT_SECONDS}s)"
    )

    class Config:
        # Optional: enforce strict schema (no extra fields allowed)
        extra = Extra.forbid


def _format_error(e: ValidationError) -> str:
    """
    Returns a pretty JSON string from a ValidationError.
    """
    return e.json(indent=2)


def validate_transaction(
    data: dict,
    log_errors: bool = True,
    strict: bool = True
) -> Tuple[bool, Union[Contribution, str]]:
    """
    Validates incoming transaction data against the Contribution schema.

    Args:
        data (dict): The transaction data to validate.
        log_errors (bool): If True, logs validation errors.
        strict (bool): If True, forbids extra fields.

    Returns:
        Tuple[bool, Contribution or str]: 
            - (True, Contribution) if valid,
            - (False, error JSON string) if invalid.
    """
    schema = Contribution
    if not strict:
        class ContributionRelaxed(Contribution):
            class Config:
                extra = Extra.allow
        schema = ContributionRelaxed

    try:
        contribution = schema(**data)
        return True, contribution
    except ValidationError as e:
        err_json = _format_error(e)
        if log_errors:
            logger.warning(f"Validation failed: {err_json}")
        return False, err_json


def validate_transactions(
    transactions: List[dict],
    log_errors: bool = True,
    strict: bool = True
) -> Tuple[bool, List[Contribution], List[str]]:
    """
    Validates a list of transactions.

    Args:
        transactions (List[dict]): List of transaction dicts.
        log_errors (bool): If True, logs validation errors.
        strict (bool): If True, forbids extra fields.

    Returns:
        Tuple[bool, List[Contribution], List[str]]:
            - True if all are valid, otherwise False.
            - List of valid Contribution objects.
            - List of error messages (if any).
    """
    valid_contributions = []
    errors = []
    all_valid = True

    for i, tx in enumerate(transactions):
        valid, result = validate_transaction(tx, log_errors=log_errors, strict=strict)
        if valid:
            valid_contributions.append(result)
        else:
            all_valid = False
            errors.append(f"Transaction {i}: {result}")

    return all_valid, valid_contributions, errors

