# src/peoples_coin/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
from celery import Celery

# --- Standard Flask Extensions ---
# These are instantiated here and will be initialized in the factory (init_app).

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
swagger = Swagger()

# The key_func tells the limiter how to identify a client (by their IP address).
limiter = Limiter(key_func=get_remote_address)

# Celery is defined here but configured in the factory to get app context.
celery = Celery(__name__)


# --- Custom Application Systems ---
# Following the same pattern, we can define placeholders for your custom systems.
# This makes them easily importable across the application without circular dependencies.
# You will need to import your actual system classes here.

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
