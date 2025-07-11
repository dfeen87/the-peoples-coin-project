import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import your app factory and db object
from peoples_coin import create_app, db

# Get the absolute path to root alembic.ini
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
alembic_ini_path = os.path.join(base_dir, 'alembic.ini')

# Use root alembic.ini to configure logging
fileConfig(alembic_ini_path)

# Alembic Config object, provides access to values in alembic.ini
config = context.config
config.config_file_name = alembic_ini_path

# Create Flask app instance
app = create_app()

# Set the SQLAlchemy URL from Flask config into Alembic config
config.set_main_option('sqlalchemy.url', app.config['SQLALCHEMY_DATABASE_URI'])

# This is your metadata object for 'autogenerate' support
target_metadata = db.metadata


def run_migrations_offline():
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


def run_migrations_online():
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

