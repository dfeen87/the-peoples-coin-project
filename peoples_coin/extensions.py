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

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
