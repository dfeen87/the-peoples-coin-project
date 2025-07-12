"""
did_registry.py
Provides DID (Decentralized Identifier) registry utilities.
This module acts as a clean interface between the API layer and the core
database-backed consensus logic.
"""

import logging
from typing import Dict, List, Any
from flask import current_app
import validators

# --- Import the singleton accessor from the consensus module ---
from .consensus import get_consensus_instance

logger = logging.getLogger(__name__)

def register_node(node_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates node info and registers a new node via the consensus system.

    Args:
        node_info (dict): Information about the node.

    Returns:
        dict: Standardized response with success status, message, and optional data.
    """
    if not isinstance(node_info, dict):
        return {"success": False, "message": "Node information must be a valid JSON object."}

    node_id = str(node_info.get("id", "")).strip()
    node_address = str(node_info.get("address", "")).strip()

    if not node_id or not node_address:
        return {"success": False, "message": "Both 'id' and 'address' are required fields."}

    if not validators.url(node_address):
        return {"success": False, "message": "Invalid 'address' format; must be a valid URL."}

    try:
        consensus_instance = get_consensus_instance(app=current_app)
        result = consensus_instance.register_node(node_id, {"address": node_address})

        # Assume consensus returns a dict with 'success' key or adapt here accordingly
        if isinstance(result, dict) and result.get("success", True):
            return {"success": True, "message": f"Node '{node_id}' registered successfully.", "data": result}
        else:
            return {"success": False, "message": f"Failed to register node '{node_id}'.", "data": result}

    except Exception as e:
        logger.error(f"Error registering node '{node_id}': {e}", exc_info=True)
        return {"success": False, "message": "Internal server error during node registration."}


def get_all_nodes(include_metadata: bool = False) -> Dict[str, Any]:
    """
    Returns the list of all registered nodes from the consensus system.

    Args:
        include_metadata (bool): If True, includes any available node metadata.

    Returns:
        dict: Standardized response with success status, message, and node list.
    """
    try:
        consensus_instance = get_consensus_instance(app=current_app)
        status = consensus_instance.get_consensus_status()
        nodes = status.get("nodes", [])

        if not nodes:
            return {"success": True, "message": "No nodes registered.", "data": []}

        if include_metadata:
            node_list = [
                {
                    "id": node_id,
                    "info": consensus_instance.nodes.get(node_id, {})
                }
                for node_id in nodes
            ]
        else:
            node_list = [{"id": node_id} for node_id in nodes]

        return {"success": True, "message": f"Retrieved {len(node_list)} nodes.", "data": node_list}

    except Exception as e:
        logger.error(f"Error retrieving nodes: {e}", exc_info=True)
        return {"success": False, "message": "Internal server error while retrieving nodes.", "data": []}


def reset_nodes() -> Dict[str, Any]:
    """
    Clears the node registry in the consensus system.

    Returns:
        dict: Confirmation message with success status.
    """
    try:
        consensus_instance = get_consensus_instance(app=current_app)
        consensus_instance.reset_nodes()
        logger.info("All nodes have been reset in the consensus system.")
        return {"success": True, "message": "All nodes have been reset."}
    except Exception as e:
        logger.error(f"Error resetting nodes: {e}", exc_info=True)
        return {"success": False, "message": "Internal server error during nodes reset."}

