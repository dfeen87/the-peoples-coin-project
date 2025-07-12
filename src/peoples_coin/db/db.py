# peoples_coin/peoples_coin/db/db.py

from flask_sqlalchemy import SQLAlchemy

# This db object is the single source of truth for your database connection
# and provides the base class for your models to inherit from (db.Model).
db = SQLAlchemy()

