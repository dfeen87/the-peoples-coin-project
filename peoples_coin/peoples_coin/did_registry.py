"""
did_registry.py
Provides DID (Decentralized Identifier) registry utilities.
This module acts as a clean interface between the API layer and the core
database-backed consensus logic.
"""

import logging
from typing import Dict, List, Any
from flask import current_app

# --- Import the singleton accessor from the consensus module ---
from .consensus import get_consensus_instance

logger = logging.getLogger(__name__)


def register_node(node_info: Dict) -> Dict[str, Any]:
    """
    Validates node info and registers a new node via the consensus system.

    Args:
        node_info (dict): Information about the node.

    Returns:
        dict: Confirmation or error dictionary.
    """
    if not isinstance(node_info, dict):
        return {"error": "Node information must be a valid JSON object."}

    node_id = str(node_info.get("id", "")).strip()
    node_address = str(node_info.get("address", "")).strip()

    if not node_id or not node_address:
        return {"error": "Both 'id' and 'address' are required fields."}

    # Get the consensus instance, passing the current app context.
    # This is required for the first initialization.
    consensus_instance = get_consensus_instance(app=current_app)

    # Call the method on the instance
    return consensus_instance.register_node(node_id, {"address": node_address})


def get_all_nodes(include_metadata: bool = False) -> List[Dict[str, Any]]:
    """
    Returns the list of all registered nodes from the consensus system.

    Args:
        include_metadata (bool): If True, includes any available node metadata.

    Returns:
        list: A list of node dictionaries.
    """
    consensus_instance = get_consensus_instance(app=current_app)
    status = consensus_instance.get_consensus_status()
    nodes = status.get("nodes")

    if not nodes:
        return []
    
    # This part can remain simple as the consensus status provides the list directly
    if include_metadata:
        # Assuming get_consensus_status() returns nodes with metadata if requested
        # For now, we adapt to the current status structure
        node_list_with_metadata = []
        for node_id in nodes:
            node_list_with_metadata.append({
                "id": node_id,
                "info": consensus_instance.nodes.get(node_id)
            })
        return node_list_with_metadata
    else:
        return [{"id": node_id} for node_id in nodes]


def reset_nodes() -> Dict[str, str]:
    """
    Clears the node registry in the consensus system.

    Returns:
        dict: Confirmation message.
    """
    consensus_instance = get_consensus_instance(app=current_app)
    consensus_instance.reset_nodes()
    logger.info("All nodes have been reset in the consensus system.")
    return {"message": "All nodes have been reset."}
