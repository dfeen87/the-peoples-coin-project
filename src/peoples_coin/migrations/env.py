import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# --- Add project root to path to allow imports ---
# This ensures we can import your models and extensions
# Adjust this path if your project structure is different, it should point to the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# --- Alembic Config object ---
config = context.config

# --- Setup Logging ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- 1. Get Target Metadata ---
# IMPORTANT: You need to import your SQLAlchemy Base or declarative base metadata here.
# Assuming your models are defined in 'peoples_coin.models.models' and expose a 'Base.metadata'
# or a 'db.metadata' from an extension.
# Based on our previous chats, it seems 'peoples_coin.extensions.db' is where your SQLAlchemy instance resides.
try:
    from peoples_coin.extensions import db
    # Ensure this is the correct metadata object that contains all your model definitions
    target_metadata = db.metadata
except ImportError as e:
    print(f"Could not import db.metadata: {e}. Please ensure peoples_coin.extensions is correctly structured.")
    # If db.metadata is not found, you might need to import your declarative base metadata directly
    # from your models file if you have one, e.g.:
    # from peoples_coin.models.your_models_file import Base
    # target_metadata = Base.metadata
    target_metadata = None # Set to None or raise an error if metadata can't be found


# --- 2. Get Database URL ---
# Get the DB URL from the same environment variable your app uses
db_uri = os.getenv('POSTGRES_DB_URI')
if not db_uri:
    # Fallback to local PostgreSQL if the env var isn't set, using your alembic.ini setting
    db_uri = config.get_main_option('sqlalchemy.url')
    if not db_uri:
        # Fallback to local SQLite for development if the env var isn't set and no url in ini
        instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'instance')
        os.makedirs(instance_path, exist_ok=True)
        db_file_path = os.path.join(instance_path, 'peoples_coin.sqlite')
        db_uri = f"sqlite:///{db_file_path}"

# Set the sqlalchemy.url in the Alembic config for the runner
config.set_main_option('sqlalchemy.url', db_uri)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
