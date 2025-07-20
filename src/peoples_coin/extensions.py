from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import system classes
from peoples_coin.systems.immune_system import ImmuneSystem
from peoples_coin.systems.cognitive_system import CognitiveSystem

# Instantiate singletons here
immune_system = ImmuneSystem()
cognitive_system = CognitiveSystem()

