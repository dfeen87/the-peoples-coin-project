# src/peoples_coin/test_extensions.py

import sys
import os

print("sys.path before modification:")
for p in sys.path:
    print(p)

# Add 'src' folder to sys.path explicitly (relative to this file's location)
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

print("\nsys.path after modification:")
for p in sys.path:
    print(p)

# Now import your modules
from peoples_coin.extensions import db, migrate, cors, limiter, swagger, celery


from flask import Flask
from peoples_coin.extensions import db, migrate, cors, limiter, swagger, celery

def create_test_app():
    app = Flask(__name__)
    
    # Minimal config for extensions (adjust as needed)
    app.config.update({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",  # In-memory DB for testing
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "CELERY_BROKER_URL": "redis://localhost:6379/0",  # Or any valid broker url
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
        "SWAGGER": {"title": "Test API", "uiversion": 3},
        "RATELIMIT_DEFAULT": "5 per minute",
        "CORS_ORIGINS": ["*"],
    })

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    limiter.init_app(app)
    swagger.init_app(app)

    # Configure Celery
    celery.conf.broker_url = app.config["CELERY_BROKER_URL"]
    celery.conf.result_backend = app.config["CELERY_RESULT_BACKEND"]
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask

    with app.app_context():
        # Try simple db operation (create tables) to check db init
        db.create_all()

    print("✅ All extensions initialized successfully!")

    return app

if __name__ == "__main__":
    create_test_app()

