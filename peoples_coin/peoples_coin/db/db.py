# peoples_coin/peoples_coin/db/db.py

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base

# Initialize the SQLAlchemy instance. This will be integrated with your Flask app.
db = SQLAlchemy()

# Define the declarative base. Your SQLAlchemy models will inherit from this Base.
Base = declarative_base()
