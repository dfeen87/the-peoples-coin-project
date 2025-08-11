from celery import Celery
import os

def make_celery(app=None, include_tasks=None):
    """
    Creates and configures a Celery instance tied to the Flask app context.
    - Loads broker and backend URLs from environment variables.
    - Ensures tasks run within Flask app context.
    - Allows passing additional task modules to include.
    
    Args:
        app: Flask application instance (optional).
        include_tasks: list of task module strings to include.
        
    Returns:
        Configured Celery instance.
    """
    # Use explicit env vars with fallback to a sensible default Redis URL
    broker_url = os.getenv('CELERY_BROKER_URL') or os.getenv('REDIS_URL') or 'redis://localhost:6379/0'
    backend_url = os.getenv('CELERY_RESULT_BACKEND') or os.getenv('REDIS_URL') or 'redis://localhost:6379/0'
    
    if include_tasks is None:
        include_tasks = ['peoples_coin.ai_processor.processor']  # Default task modules
    
    celery = Celery(
        'peoples_coin',
        broker=broker_url,
        backend=backend_url,
        include=include_tasks
    )
    
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        # Optional: set default task time limits and retry policy
        task_soft_time_limit=300,   # seconds, adjust as needed
        task_time_limit=600,
        task_annotations={
            '*': {'rate_limit': '10/s'}  # Example: limit all tasks to 10/sec
        },
        # Add other Celery config options here if needed
    )
    
    if app is not None:
        # Bind Celery tasks to Flask app context
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        
        celery.Task = ContextTask
    
    return celery

