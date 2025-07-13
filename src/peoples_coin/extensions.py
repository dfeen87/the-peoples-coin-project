# src/peoples_coin/extensions.py

from flask_sqlalchemy import SQLAlchemy

# Initialize the shared SQLAlchemy database instance
db = SQLAlchemy()

# Import system instances from the systems subpackage
from .systems.immune_system import immune_system
from .systems.cognitive_system import cognitive_system
from .systems.endocrine_system import endocrine_system
from .systems.circulatory_system import circulatory_system

