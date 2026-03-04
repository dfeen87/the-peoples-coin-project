from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
from celery import Celery
from flask_redis import FlaskRedis  # <<-- THIS IS THE MISSING IMPORT

# --- Flask Extensions ---
db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
swagger = Swagger()
limiter = Limiter(key_func=get_remote_address)
celery = Celery(__name__)
redis_client = FlaskRedis()

def make_celery(app=None):
    """Initializes a Celery instance with a Flask application context."""
    from peoples_coin.factory import create_app
    app = app or create_app()
    celery.conf.update(app.config)

    # Apply serialization, time limits, and rate limit settings
    # Task modules can be configured via CELERY_INCLUDE_TASKS in app config
    include_tasks = app.config.get(
        'CELERY_INCLUDE_TASKS', ['peoples_coin.ai_processor.processor']
    )
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_soft_time_limit=300,
        task_time_limit=600,
        task_annotations={
            '*': {'rate_limit': '10/s'}
        },
        include=include_tasks,
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
