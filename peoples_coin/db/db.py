# peoples_coin/db/db.py

from flask_sqlalchemy import SQLAlchemy

# This db object is the single source of truth for your database connection
# and provides the db.Model base class for your models.
db = SQLAlchemy()
