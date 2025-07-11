"""
did_registry.py
Provides DID (Decentralized Identifier) registry utilities for The People’s Coin skeleton system.
"""

import logging
from typing import Dict, List, Optional

# --- CRITICAL CHANGE: Updated to absolute import ---
from peoples_coin import consensus # Changed from: from consensus import (
                                # register_node as consensus_register_node,
                                # get_consensus_status,
                                # reset_nodes as consensus_reset_nodes,
                                # )

logger = logging.getLogger(__name__)


def register_node(node_info: Dict) -> Dict[str, str]:
    """
    Registers a new node through the consensus system.

    Args:
        node_info (dict): Information about the node, e.g., {'id': 'node1', 'address': 'http://...'}

    Returns:
        dict: Confirmation message and current total nodes count, or error.
    """
    node_id = str(node_info.get("id", "")).strip()
    node_address = str(node_info.get("address", "")).strip()

    if not node_id:
        logger.error("Missing or empty 'id' in node_info.")
        return {"error": "'id' is required to register a node."}
    if not node_address:
        logger.error("Missing or empty 'address' in node_info.")
        return {"error": "'address' is required to register a node."}

    logger.info(f"Attempting to register node '{node_id}' at '{node_address}'")
    # --- CRITICAL CHANGE: Updated function call to use 'consensus.' prefix ---
    result = consensus.register_node(node_id, {"address": node_address})

    if "error" in result:
        logger.warning(f"Consensus error during node registration: {result}")
        return result

    total_nodes = len(get_all_nodes())
    logger.info(f"Node '{node_id}' registered successfully. Total nodes: {total_nodes}")

    return {
        "message": f"Node '{node_id}' registered successfully.",
        "total_nodes": str(total_nodes)
    }


def get_all_nodes() -> List[Dict[str, str]]:
    """
    Returns the list of all registered nodes from the consensus system.

    Returns:
        list: List of node info dicts: [{'id': ...}, ...]
    """
    # --- CRITICAL CHANGE: Updated function call to use 'consensus.' prefix ---
    status = consensus.get_consensus_status()
    nodes = status.get("nodes")

    if nodes is None:
        logger.error("Consensus status returned no 'nodes' field.")
        return []

    # If future consensus exposes metadata, adjust here
    return [{"id": node_id} for node_id in nodes]


def get_all_nodes_with_metadata() -> List[Dict[str, Optional[Dict]]]:
    """
    Optional: Returns all registered nodes including metadata if available.

    Returns:
        list: [{'id': ..., 'info': {...}}, ...]
    """
    # --- CRITICAL CHANGE: Updated function call to use 'consensus.' prefix ---
    status = consensus.get_consensus_status()
    nodes = status.get("nodes")

    if nodes is None:
        logger.error("Consensus status returned no 'nodes' field.")
        return []

    if isinstance(nodes, dict):
        # if consensus exposes dict with metadata
        return [{"id": k, "info": v} for k, v in nodes.items()]
    else:
        # fallback if nodes is just a list
        return [{"id": node_id, "info": None} for node_id in nodes]


def reset_nodes() -> Dict[str, str]:
    """
    Clears the node registry in the consensus system.

    Returns:
        dict: Confirmation message.
    """
    # --- CRITICAL CHANGE: Updated function call to use 'consensus.' prefix ---
    consensus.reset_nodes()
    logger.info("All nodes have been reset.")
    return {"message": "All nodes have been reset."}
