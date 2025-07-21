import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# --- Add project root to path to allow imports ---
# This ensures we can import your models and extensions
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# --- Alembic Config object ---
config = context.config

# --- Setup Logging ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- 1. Get Target Metadata ---
# Import your extensions and models directly
from peoples_coin.extensions import db
from peoples_coin.models import models # Make sure this import grabs all your models

target_metadata = db.metadata

# --- 2. Get Database URL ---
# Get the DB URL from the same environment variable your app uses
db_uri = os.getenv('POSTGRES_DB_URI')
if not db_uri:
    # Fallback to local SQLite for development if the env var isn't set
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
