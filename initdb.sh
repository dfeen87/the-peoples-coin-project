#!/bin/bash
# Script to initialize the database

echo "Initializing Peoples Coin database..."

# Navigate to the project root
# cd "$(dirname "$0")"

# Activate the virtual environment
source venv/bin/activate

# Run Alembic migrations to create tables
alembic upgrade head

# Or run a Python script for database initialization
# python db/init_db.py

echo "Database initialization complete."
