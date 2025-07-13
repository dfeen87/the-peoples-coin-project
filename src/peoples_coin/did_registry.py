import logging
from typing import Dict, List, Any, Union

from pydantic import BaseModel, Field, ValidationError, field_validator
import validators

# --- Import the application's consensus system instance ---
# This follows the Flask extension pattern for a decoupled, testable architecture.
from .. import consensus

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. Pydantic Models for Robust Input Validation and Standardized Responses
# ==============================================================================

class NodeRegistrationModel(BaseModel):
    """Defines the schema for registering a new node."""
    id: str = Field(..., min_length=3, max_length=64, description="The unique identifier for the node.")
    address: str = Field(..., description="The network address (URL) of the node.")

    @field_validator('address')
    @classmethod
    def validate_address_url(cls, v: str) -> str:
        """Validates that the node address is a valid URL."""
        if not validators.url(v):
            raise ValueError("Node address must be a valid URL.")
        return v

class ServiceResponse(BaseModel):
    """A standardized response model for service layer functions."""
    success: bool
    message: str
    data: Any = None


# ==============================================================================
# 2. Service Layer Functions
# ==============================================================================

def register_node(node_info: Dict[str, Any]) -> ServiceResponse:
    """
    Validates node info using Pydantic and registers a new node via the consensus system.
    """
    try:
        # Use Pydantic for robust, declarative validation.
        node_data = NodeRegistrationModel(**node_info)
    except ValidationError as e:
        logger.warning(f"Node registration validation failed: {e.errors()}")
        return ServiceResponse(success=False, message="Invalid node data provided.", data=e.errors())

    try:
        # Call the consensus system to perform the core logic.
        result = consensus.register_node(node_id=node_data.id, address=node_data.address)
        
        if result.get("status") == "registered":
            return ServiceResponse(success=True, message=f"Node '{node_data.id}' registered successfully.", data=result)
        else:
            return ServiceResponse(success=False, message=f"Node '{node_data.id}' may already exist or an error occurred.", data=result)

    except Exception as e:
        logger.error(f"Error registering node '{node_data.id}': {e}", exc_info=True)
        return ServiceResponse(success=False, message="An internal server error occurred during node registration.")


def get_all_nodes() -> ServiceResponse:
    """
    Returns the list of all registered nodes from the consensus system.
    """
    try:
        status = consensus.get_consensus_status()
        nodes = status.get("nodes", [])

        if not nodes:
            return ServiceResponse(success=True, message="No nodes are currently registered.", data=[])

        return ServiceResponse(success=True, message=f"Retrieved {len(nodes)} registered nodes.", data=nodes)

    except Exception as e:
        logger.error(f"Error retrieving nodes: {e}", exc_info=True)
        return ServiceResponse(success=False, message="An internal server error occurred while retrieving nodes.")


def reset_all_nodes() -> ServiceResponse:
    """
    Resets the consensus system by clearing all nodes and re-electing a leader.
    This is a destructive operation intended for testing or administrative purposes.
    """
    try:
        # The core logic is now encapsulated in the Consensus class.
        consensus.reset_nodes_and_elect_leader()
        logger.info("All nodes have been reset in the consensus system.")
        return ServiceResponse(success=True, message="All nodes have been successfully reset.")
    except Exception as e:
        logger.error(f"Error resetting nodes: {e}", exc_info=True)
        return ServiceResponse(success=False, message="An internal server error occurred during the node reset.")


