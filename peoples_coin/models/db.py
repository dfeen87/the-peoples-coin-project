from flask_sqlalchemy import SQLAlchemy
from peoples_coin.db_types import JSONType, UUIDType, EnumType

# This db object is the single source of truth for your database connection
# and provides the base class for your models to inherit from (db.Model).
db = SQLAlchemy()