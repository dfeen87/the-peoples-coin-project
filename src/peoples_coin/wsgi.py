"""
WSGI entry point for the Peoples Coin Flask application.

This file is used by WSGI servers like Gunicorn or uWSGI to run the app.
"""

import logging
from peoples_coin import create_app

# Create Flask application instance using default config
app = create_app()

# Optional: Setup logging here if needed (or rely on app's own logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Peoples Coin WSGI application starting up.")

# If running standalone (not via Gunicorn/uWSGI), enable debug server
if __name__ == "__main__":
    # Running Flask's built-in server for local development/testing
    app.run(host="0.0.0.0", port=5000, debug=True)

