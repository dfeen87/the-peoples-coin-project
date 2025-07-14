from celery import Celery
import os

# Load broker and backend URLs from environment variables or default to local Redis
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
backend_url = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

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
)

# Optional: if your tasks need Flask app context, create a helper function like this
def init_celery(app):
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery

