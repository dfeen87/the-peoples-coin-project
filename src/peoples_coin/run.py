import os
from dotenv import load_dotenv

# Load environment variables from a .env file at the project root.
# This should be the very first thing that happens.
load_dotenv()

# Import the create_app factory from your main application package.
from peoples_coin import create_app

# Get the application instance by calling the factory.
# You can pass a config name for different environments, e.g., 'development' or 'testing'.
app = create_app()

if __name__ == '__main__':
    # This block is only for running the local development server.
    # For production, you would use a proper WSGI server like Gunicorn or Waitress.
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('FLASK_PORT', 5000)),
        debug=app.config.get('DEBUG', False)
    )

