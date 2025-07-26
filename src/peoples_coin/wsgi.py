"""
WSGI entry point for the Peoples Coin Flask application.

This file is used by WSGI servers like Gunicorn to run the app.
"""

import os
import sys
import logging

# Set up basic logging for the WSGI entry point itself
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Ensure the project's 'src' directory is on the Python path
# This is usually handled by PYTHONPATH in Dockerfile, but explicit insert can add robustness
# However, for Cloud Run, it's often best to rely solely on Dockerfile's PYTHONPATH
# and remove redundant path manipulation here.
# For now, let's remove it to simplify, as PYTHONPATH=/app/src is already correct.
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from peoples_coin.factory import create_app

# Create Flask application instance using default config
# Gunicorn will load this 'app' variable.
app = create_app()

logger.info("Peoples Coin WSGI application instance created.")

# The __main__ block should ONLY be for local development with Flask's built-in server.
# It should NOT run when Gunicorn is managing the app.
if __name__ == "__main__":
    logger.warning("Running Flask development server directly. Use Gunicorn for production.")
    # Cloud Run provides the PORT environment variable.
    # For local development, default to 8080 to match Dockerfile EXPOSE.
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True) # Keep debug=True for local dev

