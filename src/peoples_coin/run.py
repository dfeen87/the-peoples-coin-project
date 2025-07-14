import os
import logging
from dotenv import load_dotenv

load_dotenv()

from peoples_coin import create_app, endocrine_system, cognitive_system

# Import celery and the helper
from celery_app import celery, init_celery

app = create_app()

# Initialize celery with the Flask app context
celery = init_celery(app)

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    with app.app_context():
        logger.info("Starting Endocrine System...")
        endocrine_system.start()
        logger.info("Starting Cognitive System background loop...")
        cognitive_system.start_background_loop()

        logger.info("Celery initialized and ready to process tasks.")

    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5000)))
    logger.info(f"Starting Flask server on 0.0.0.0:{port}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=app.config.get('DEBUG', False)
    )

