"""
System metrics collection for the Global Observability Node.

This module provides functions to safely collect system metrics
including CPU, memory, disk, and database statistics.
"""
import os
import psutil
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_system_metrics() -> Dict[str, Any]:
    """
    Collect current system metrics using psutil.
    
    Returns:
        dict: System metrics including CPU, memory, disk, and load averages
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Load averages (1, 5, 15 minutes) - Unix only
        try:
            load_avg = os.getloadavg()
            load_averages = {
                "1min": load_avg[0],
                "5min": load_avg[1],
                "15min": load_avg[2]
            }
        except (AttributeError, OSError):
            # Windows doesn't have getloadavg
            load_averages = {
                "1min": None,
                "5min": None,
                "15min": None
            }
        
        return {
            "cpu_percent": cpu_percent,
            "memory": {
                "total_mb": memory.total / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
                "used_mb": memory.used / (1024 * 1024),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": disk.total / (1024 * 1024 * 1024),
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
                "percent": disk.percent
            },
            "load_averages": load_averages,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error collecting system metrics: {e}", exc_info=True)
        return {
            "error": "Failed to collect system metrics",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


def get_redis_queue_depth(redis_client) -> Optional[int]:
    """
    Get Redis queue depth if Redis is available.
    
    Args:
        redis_client: Flask-Redis client instance
        
    Returns:
        int or None: Queue depth or None if Redis is unavailable
    """
    try:
        if redis_client and hasattr(redis_client, 'connection_pool'):
            # Try to get Celery queue depth
            # This is a simplified version - actual queue name may vary
            queue_name = "celery"
            depth = redis_client.llen(queue_name)
            return depth
    except Exception as e:
        logger.warning(f"Could not get Redis queue depth: {e}")
    
    return None


def get_db_activity(db_session) -> Dict[str, Any]:
    """
    Get recent database activity metrics.
    
    Args:
        db_session: SQLAlchemy database session
        
    Returns:
        dict: Database activity metrics
    """
    try:
        from sqlalchemy import text
        
        # Get recent query counts and basic stats
        # Note: This queries pg_stat_database for PostgreSQL
        query = text("""
            SELECT 
                numbackends as active_connections,
                xact_commit as transactions_committed,
                xact_rollback as transactions_rolled_back,
                blks_read as blocks_read,
                blks_hit as blocks_hit,
                tup_returned as tuples_returned,
                tup_fetched as tuples_fetched,
                tup_inserted as tuples_inserted,
                tup_updated as tuples_updated,
                tup_deleted as tuples_deleted
            FROM pg_stat_database 
            WHERE datname = current_database()
            LIMIT 1
        """)
        
        result = db_session.execute(query).fetchone()
        
        if result:
            return {
                "active_connections": result.active_connections,
                "transactions_committed": result.transactions_committed,
                "transactions_rolled_back": result.transactions_rolled_back,
                "blocks_read": result.blocks_read,
                "blocks_hit": result.blocks_hit,
                "cache_hit_ratio": (
                    result.blocks_hit / (result.blocks_hit + result.blocks_read) * 100
                    if (result.blocks_hit + result.blocks_read) > 0 else 0
                ),
                "tuples_returned": result.tuples_returned,
                "tuples_fetched": result.tuples_fetched,
                "tuples_inserted": result.tuples_inserted,
                "tuples_updated": result.tuples_updated,
                "tuples_deleted": result.tuples_deleted,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        return {"error": "No database statistics available"}
        
    except Exception as e:
        logger.error(f"Error getting database activity: {e}", exc_info=True)
        return {"error": "Failed to get database activity"}


def is_kubernetes_enabled() -> bool:
    """
    Check if running in a Kubernetes environment.
    
    Returns:
        bool: True if Kubernetes environment is detected
    """
    # Check for common Kubernetes environment variables
    k8s_indicators = [
        'KUBERNETES_SERVICE_HOST',
        'KUBERNETES_SERVICE_PORT',
        'K_SERVICE',  # Cloud Run (which is built on Kubernetes)
    ]
    
    return any(os.environ.get(indicator) for indicator in k8s_indicators)
