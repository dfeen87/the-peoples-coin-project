import logging
from logging.config import fileConfig

from flask import current_app
from alembic import context

# Alembic Config object, provides access to .ini file values.
config = context.config

# Set up Python logging from config file.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    """
    Get SQLAlchemy engine from Flask-Migrate extension.
    Supports Flask-SQLAlchemy v2 and v3+ compatibility.
    """
    try:
        # Flask-SQLAlchemy < 3
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # Flask-SQLAlchemy >= 3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    """
    Get DB connection URL as string, for offline migration mode.
    """
    try:
        return get_engine().url.render_as_string(hide_password=False).replace('%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


def get_metadata():
    """
    Get the metadata object for Alembic autogenerate support.
    """
    target_db = current_app.extensions['migrate'].db
    if hasattr(target_db, 'metadatas'):
        # Flask-SQLAlchemy >= 3 supports multiple metadata
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """
    Run migrations in 'offline' mode.
    Uses URL string and skips DBAPI connection.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """
    Run migrations in 'online' mode.
    Creates an Engine and connects for running migrations.
    """

    # Prevent auto-generation when no schema changes detected
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

