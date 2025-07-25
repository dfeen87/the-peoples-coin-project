# run.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file for local development.
# This should be the first thing to run.
load_dotenv()

# Import the application factory from our structured application
from peoples_coin.factory import create_app

# Create the Flask app instance using the factory
# The factory now handles all setup (logging, extensions, routes, etc.)
app = create_app()

# This block allows running the Flask development server directly
# using the command `python run.py`.
# For production, you will use a WSGI server like Gunicorn.
if __name__ == '__main__':
    # The port and debug settings are pulled from the config object inside the app
    port = int(os.environ.get('PORT', 5001))
    debug_mode = app.config.get("DEBUG", False)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
