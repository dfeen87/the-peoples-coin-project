"""
extensions.py

Initialize shared Flask extensions and system instances.
"""

from flask_sqlalchemy import SQLAlchemy

# Initialize the shared SQLAlchemy database instance
db = SQLAlchemy()

# Import system instances from the systems subpackage (absolute imports)
from peoples_coin.systems.immune_system import immune_system
from peoples_coin.systems.cognitive_system import cognitive_system
from peoples_coin.systems.endocrine_system import endocrine_system
from peoples_coin.systems.circulatory_system import circulatory_system

