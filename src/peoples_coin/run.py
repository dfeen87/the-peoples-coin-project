import os
import logging
from dotenv import load_dotenv

load_dotenv()

from peoples_coin import create_app

# Initialize the Flask app
app = create_app()

# Set up logging for production
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Export the app for Gunicorn to use:
# gunicorn -w 4 -b 0.0.0.0:$PORT run:app

# Note: Do NOT start background loops here — 
# those should be handled by dedicated worker processes or init scripts.

if __name__ == '__main__':
    # This block is only for local dev/debug (optional)
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting local Flask dev server on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)

