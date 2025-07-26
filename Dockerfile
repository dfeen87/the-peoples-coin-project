# Use a modern Python base image for a lean production environment
FROM python:3.11-alpine

# Set environment variables for Python and Flask application
LABEL build_version="20250726.4-alpine"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src:/usr/local/lib/python3.11/site-packages

# Create a non-root user and group for enhanced security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup -D -h /app -s /bin/bash appuser

# Set the working directory inside the container
WORKDIR /app

# Install system-level dependencies required by Python packages
# build-base: For compiling C extensions (e.g., psycopg2-binary, cryptography)
# libffi-dev, openssl-dev: For cryptography
# postgresql-dev: PostgreSQL headers for psycopg2
# bash: Useful for scripting or shell use
RUN apk update && apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    postgresql-dev \
    bash

# Copy the Python dependency list file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy your application source code into the container
COPY src/ src/

# Change ownership of the /app directory to the non-root user
RUN chown -R appuser:appgroup /app

# Switch to the non-root user for running the application
USER appuser

# Expose the port on which the application will listen
EXPOSE 8080

# Start the application using Gunicorn WSGI server
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]

