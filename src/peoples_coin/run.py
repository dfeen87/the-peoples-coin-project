import os
from dotenv import load_dotenv

# Load environment variables from a .env file at the project root.
load_dotenv()

# Import the create_app factory and the system objects that need to be started.
from peoples_coin import create_app, endocrine_system, cognitive_system

# Get the application instance by calling the factory.
# This creates the app but does NOT start the background threads.
app = create_app()

# This is the main execution block for running the development server.
if __name__ == '__main__':
    # ==================================================================
    # THIS IS THE KEY CHANGE
    # We start the background systems here, only when running the server.
    # We must do it within the application context.
    # ==================================================================
    with app.app_context():
        endocrine_system.start()
        cognitive_system.start_background_loop()

    # Run the Flask development server.
    # For production, you would use a proper WSGI server like Gunicorn.
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('FLASK_PORT', 5000)),
        debug=app.config.get('DEBUG', False)
    )

