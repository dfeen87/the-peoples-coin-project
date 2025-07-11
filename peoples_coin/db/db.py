# peoples_coin/db/db.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base

db = SQLAlchemy()
Base = declarative_base()

# Bind the metadata of Base to the db engine dynamically
def bind_base_metadata(app):
    Base.metadata.bind = db.engine

# Optional: If you want to use Base for models, ensure you call bind_base_metadata(app) after app creation.

