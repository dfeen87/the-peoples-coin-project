# src/peoples_coin/extensions.py

from flask_sqlalchemy import SQLAlchemy

# Import all your system classes
from .systems.immune_system import ImmuneSystem
from .systems.cognitive_system import CognitiveSystem
from .systems.endocrine_system import EndocrineSystem
from .systems.circulatory_system import CirculatorySystem
# ==================================================================
# THIS IS THE CORRECTED IMPORT
# It now correctly points to peoples_coin/consensus.py
# ==================================================================
from .consensus import Consensus

# Create the instances of all your systems here, in one central place.
db = SQLAlchemy()
immune_system = ImmuneSystem()
cognitive_system = CognitiveSystem()
endocrine_system = EndocrineSystem()
circulatory_system = CirculatorySystem()
consensus = Consensus()

