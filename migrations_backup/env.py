import os
import sys
from os.path import abspath, dirname, join
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from alembic import context

# --- START: Custom additions for Flask-SQLAlchemy integration ---

# Calculate project root directory (two levels up from this file)
project_root = dirname(dirname(abspath(__file__)))

# Add 'src' folder to sys.path so we can import 'peoples_coin' package
sys.path.insert(0, join(project_root, 'src'))

# Import your SQLAlchemy db instance to get target metadata
try:
    from peoples_coin.db.db import db
    target_metadata = db.metadata
except ImportError as e:
    print(
        f"Error importing db or models: {e}. "
        f"Ensure your Python path is correct (sys.path[0] should be '{join(project_root, 'src')}') "
        f"and 'peoples_coin.db.db' is accessible.",
        file=sys.stderr
    )
    target_metadata = None

# --- END: Custom additions ---

# Alembic Config object, provides access to .ini file values
config = context.config

# Setup Python logging using the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # Obtain DB URL from config or Flask app config if missing
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        from peoples_coin import create_app
        app = create_app()
        url = app.config['SQLALCHEMY_DATABASE_URI']

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode using Flask app context."""
    from peoples_coin import create_app
    app = create_app()

    connectable = create_engine(
        app.config['SQLALCHEMY_DATABASE_URI'],
        poolclass=pool.NullPool
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

