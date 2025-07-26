# Use a modern Python base image
FROM python:3.11-slim

# Set environment variables for Python and Flask
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src

# Create a non-root user and group for security best practices
RUN groupadd --system appgroup && useradd --system -g appgroup -d /app -s /bin/bash appuser

# Set the working directory inside the container
WORKDIR /app

# Install system-level dependencies required for Python packages (e.g., psycopg2-binary, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python dependency list into the container
COPY requirements.txt .

# Install Python dependencies
# pip is upgraded first to ensure the latest version for installation stability
# --no-cache-dir reduces the image size by not storing downloaded packages
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the application source code into the container
# The 'src/' directory from your host will be copied to '/app/src/' in the container
COPY src/ src/

# Change ownership of the /app directory to the non-root user
# This ensures the appuser has permissions to run the application
RUN chown -R appuser:appgroup /app

# Switch to the non-root user for running the application
# This is a security best practice
USER appuser

# Expose the port on which the application will listen
# Cloud Run expects the application to listen on the port specified by the PORT environment variable (default 8080)
EXPOSE 8080

# Define the command to run the application
# Gunicorn is used to serve the Flask application
# -w 4: Specifies 4 worker processes (adjust based on CPU/memory)
# -b 0.0.0.0:8080: Binds Gunicorn to all network interfaces on port 8080
# peoples_coin.factory:create_app(): Tells Gunicorn to find the create_app() function
#                                   in the peoples_coin.factory module to get the Flask app instance.
CMD ["/bin/bash", "-c", "python -c 'import sys; sys.path.append(\"/app/src\"); from gunicorn.app.wsgiapp import run; run()' peoples_coin.factory:create_app()"]
