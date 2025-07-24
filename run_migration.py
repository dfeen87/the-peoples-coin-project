import os
from alembic.config import Config
from alembic import command

# --- This script manually builds the Alembic configuration ---

# Get the absolute path to the directory where this script lives
project_dir = os.path.dirname(os.path.abspath(__file__))

# Create a new AlembicConfig object in memory
alembic_cfg = Config()

# 1. Set the path to your migrations directory.
#    This MUST be an absolute path to be foolproof.
script_location = os.path.join(project_dir, 'src/peoples_coin/migrations')
alembic_cfg.set_main_option("script_location", script_location)

# 2. Set the database URL directly in the configuration.
#    This is the most important part.
postgres_url = "postgresql://donfeeney@localhost/postgres"
alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)

print("--- Running migration with explicit settings ---")
print(f"Script Location: {script_location}")
print(f"Database URL: {postgres_url}")
print("---------------------------------------------")

# 3. Run the 'upgrade' command programmatically
try:
    command.upgrade(alembic_cfg, "head")
    print("\n--- Migration completed successfully! ---")
except Exception as e:
    print(f"\n--- An error occurred during migration: {e} ---")
