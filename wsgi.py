import logging
from peoples_coin.factory import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    # This file's only job is to create the app via the factory.
    app = create_app()
    logger.info("✅ WSGI application instance created.")

except Exception as e:
    logger.exception("🚨 CRITICAL FAILURE in wsgi.py: %s", str(e))
    raise
