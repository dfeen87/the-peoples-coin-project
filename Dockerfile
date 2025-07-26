# Use a modern, slim Python base image
FROM python:3.11-slim

# Unique build version label for tracking
LABEL build_version="20250726.10-streamlined-paths"

# Environment variables for Python behavior
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/src

# Create non-root user and group for security
RUN groupadd --system appgroup && useradd --system -g appgroup -d /src -s /bin/bash appuser

# Set working directory to /src where your code will live
WORKDIR /src

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements.txt and install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r /requirements.txt

# Copy your application source code into /src
COPY src/ /src/

# Set ownership of /src to the non-root user
RUN chown -R appuser:appgroup /src

# Switch to non-root user for running the app
USER appuser

# Expose the port your app listens on
EXPOSE 8080

# Run Gunicorn pointing to your app's wsgi.py inside peoples_coin package
CMD ["gunicorn", "--chdir", "peoples_coin", "wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

