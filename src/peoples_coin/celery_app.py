from celery import Celery
import os

# Load broker and backend URLs from environment variables with sensible defaults
broker_url = os.getenv('CELERY_BROKER_URL', os.getenv('REDIS_URL', 'redis://10.128.0.4:6379/0'))
backend_url = os.getenv('CELERY_RESULT_BACKEND', os.getenv('REDIS_URL', 'redis://10.128.0.4.6379/0'))

celery = Celery(
    'peoples_coin',
    broker=broker_url,
    backend=backend_url,
    include=['peoples_coin.ai_processor.processor']  # Your task modules
)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # You can add other configurations as needed, e.g. task time limits, retries, etc.
)

def make_celery(app):
    """
    Integrates Celery with Flask app context.
    Ensures tasks have access to Flask's current_app and other context.
    """
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery

