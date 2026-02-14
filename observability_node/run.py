#!/usr/bin/env python3
"""
Standalone runner for the Global Observability Node.

This script allows the observability node to run independently
from the main API server.

Usage:
    python -m observability_node.run
    
Environment variables:
    DATABASE_URL: PostgreSQL connection string
    OBSERVABILITY_PORT: Port to bind to (default: 8080)
    CELERY_BROKER_URL: Redis connection string (optional)
"""
import os
import sys
import logging

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from observability_node.app import create_observability_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the observability node."""
    # Validate required environment variables
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL environment variable is required")
        sys.exit(1)
    
    # Get configuration
    port = int(os.environ.get('OBSERVABILITY_PORT', 8080))
    host = os.environ.get('OBSERVABILITY_HOST', '0.0.0.0')
    
    logger.info("Starting Global Observability Node...")
    logger.info(f"Binding to {host}:{port}")
    
    # Create and run the app
    app = create_observability_app()
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()
