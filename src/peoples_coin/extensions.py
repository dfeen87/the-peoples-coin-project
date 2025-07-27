# src/peoples_coin/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
from celery import Celery

# --- Flask Extensions ---
# Instantiate extensions here; initialize later in app factory with init_app(app).

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
swagger = Swagger()

# Limiter: identify clients by IP address by default
limiter = Limiter(key_func=get_remote_address)

# Celery app instance; configured with Flask app context in factory.py
celery = Celery(__name__)

# --- Custom app-specific systems (commented out for now) ---
# Import and instantiate these systems in your factory or app startup if needed.
# from .systems.immune_system import ImmuneSystem
# from .systems.cognitive_system import CognitiveSystem
# from .systems.endocrine_system import EndocrineSystem
# from .systems.circulatory_system import CirculatorySystem
# from .systems.reproductive_system import ReproductiveSystem
# from .consensus import Consensus

# immune_system = ImmuneSystem()
# cognitive_system = CognitiveSystem()
# endocrine_system = EndocrineSystem()
# circulatory_system = CirculatorySystem()
# reproductive_system = ReproductiveSystem()
# consensus_instance = Consensus()

