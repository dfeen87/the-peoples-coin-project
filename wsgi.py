"""
WSGI entry point for the Peoples Coin Flask application.
Used by Gunicorn to serve the app in production.
"""

import os
import logging

# Set up basic logging (stdout-friendly for container logging)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

try:
    # Import the app factory AFTER setting env vars, if needed
    from peoples_coin import create_app

    # Create the Flask app instance
    app = create_app()
    logger.info("✅ Peoples Coin WSGI application instance created.")

except Exception as e:
    logger.exception("🚨 Failed to create WSGI application: %s", str(e))
    raise e

# Optional: Only used if running directly via python wsgi.py (not typical in prod)
if __name__ == "__main__":
    logger.warning("⚠️  Running Flask development server directly. Use Gunicorn in production.")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)

