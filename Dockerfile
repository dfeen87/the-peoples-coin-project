# Use a modern Python base image for a lean production environment
FROM python:3.11-slim

# Set environment variables for Python and Flask application
# PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc files to disk.
# PYTHONUNBUFFERED=1: Ensures Python output is unbuffered, useful for logging in containers.
# FLASK_ENV=production: Sets Flask to production mode.
# PYTHONPATH: Crucial for Python to find your application package.
#             It includes /app/src (where your 'peoples_coin' package is)
#             and /usr/local/lib/python3.11/site-packages (where pip installs packages).

LABEL build_version="20250726.2"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src:/usr/local/lib/python3.11/site-packages

# Create a non-root user and group for enhanced security
# --system creates a system user/group, -d /app sets home directory, -s /bin/bash sets shell
RUN groupadd --system appgroup && useradd --system -g appgroup -d /app -s /bin/bash appuser

# Set the working directory inside the container
WORKDIR /app

# Install system-level dependencies required by Python packages
# build-essential: For compiling C extensions (e.g., for psycopg2-binary, cryptography).
# libffi-dev, libssl-dev: For cryptography-related packages.
# libpq-dev: For PostgreSQL client libraries (used by psycopg2-binary).
# bash: Included for shell operations, common in base images.
# rm -rf /var/lib/apt/lists/*: Cleans up apt cache to reduce image size.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python dependency list file into the container's working directory
# This allows pip to install the required packages.
COPY requirements.txt .

# Install Python dependencies
# pip install --upgrade pip: Ensures pip itself is up-to-date.
# pip install --no-cache-dir -r requirements.txt: Installs all listed packages.
# --no-cache-dir reduces the final image size.
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy your application source code into the container
# The 'src/' directory from your host machine is copied to '/app/src/' in the container.
COPY src/ src/

# Change ownership of the /app directory to the non-root user
# This ensures the 'appuser' has the necessary permissions to run the application and access its files.
RUN chown -R appuser:appgroup /app

# Switch to the non-root user for running the application
# This is a crucial security best practice to limit privileges.
USER appuser

# Expose the port on which the application will listen
# Cloud Run expects your application to listen on the port specified by the PORT environment variable (default 8080).
EXPOSE 8080

# Define the command to run the application when the container starts
# Gunicorn is the WSGI HTTP server used to serve the Flask application.
# -w 4: Specifies 4 worker processes (adjust based on container CPU/memory limits).
# -b 0.0.0.0:8080: Binds Gunicorn to all network interfaces on port 8080, making it accessible.
# peoples_coin.factory:create_app(): Tells Gunicorn to find the 'create_app()' function
#                                   within the 'peoples_coin.factory' module to get the Flask application instance.
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]
