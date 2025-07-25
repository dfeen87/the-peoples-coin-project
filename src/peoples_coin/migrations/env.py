import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# --- Add project root to path to allow imports ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# --- Alembic Config object ---
config = context.config

# --- Setup Logging ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- 1. Get Target Metadata ---
try:
    from peoples_coin.extensions import db
    target_metadata = db.metadata
except ImportError as e:
    print(f"Could not import db.metadata: {e}. Please ensure peoples_coin.extensions is correctly structured.")
    target_metadata = None

# --- 2. Get Database URL ---

# Use environment variable first (make sure your env var is set, and is raw, unescaped URL)
db_uri = os.getenv('POSTGRES_DB_URI')
if not db_uri:
    # If env var missing, fallback to URL in alembic.ini
    # Just read it but DO NOT call set_main_option to avoid interpolation errors
    db_uri = config.get_main_option('sqlalchemy.url')

if not db_uri:
    # Fallback to local SQLite if no URL found
    instance_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'instance'))
    os.makedirs(instance_path, exist_ok=True)
    db_file_path = os.path.join(instance_path, 'peoples_coin.sqlite')
    db_uri = f"sqlite:///{db_file_path}"

# **Do NOT call** config.set_main_option here with the raw URI containing % signs
# We'll use db_uri directly below in engine and context configs


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=db_uri,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Create engine config dict manually with the db_uri to avoid config interpolation
    connectable = engine_from_config(
        {"sqlalchemy.url": db_uri},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

