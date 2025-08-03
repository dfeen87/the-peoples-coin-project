import os
import sys
from logging.config import fileConfig
from urllib.parse import quote_plus

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
    from peoples_coin.models import Base
    target_metadata = Base.metadata
except ImportError:
    target_metadata = None

# --- 2. Get Database URL ---
# THIS SECTION READS YOUR CREDENTIALS FROM THE .env FILE
db_user = os.getenv('DB_USER')                  # <<< READS the DB_USER
db_password_raw = os.getenv('DB_PASSWORD')      # <<< READS the DB_PASSWORD
db_host = os.getenv('DB_HOST')                  # <<< READS the DB_HOST
db_port = os.getenv('DB_PORT', '5432')          # <<< READS the DB_PORT
db_name = os.getenv('DB_NAME')                  # <<< READS the DB_NAME
db_ssl_mode = os.getenv('DB_SSL_MODE', 'prefer')# <<< READS the DB_SSL_MODE

db_uri = None
if all([db_user, db_password_raw, db_host, db_name]):
    # This part builds the full connection string from the variables it just read
    db_password = quote_plus(db_password_raw)
    db_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?sslmode={db_ssl_mode}"
else:
    # Fallback to local SQLite if .env variables are not set
    print("Database environment variables not set, falling back to local SQLite.")
    instance_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'instance'))
    os.makedirs(instance_path, exist_ok=True)
    db_file_path = os.path.join(instance_path, 'brightacts.sqlite')
    db_uri = f"sqlite:///{db_file_path}"

# Set the URL for Alembic to use
config.set_main_option('sqlalchemy.url', db_uri)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
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
