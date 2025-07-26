# Use a modern Debian-based Python 3.11 slim image
FROM python:3.11-slim

LABEL build_version="20250726.4-debian"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src:/usr/local/lib/python3.11/site-packages

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -r appgroup && useradd -m -g appgroup -d /app appuser

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ src/

# Set permissions
RUN chown -R appuser:appgroup /app

# Diagnostic steps to verify code presence and environment
RUN echo "---- Listing /app/src directory ----" && ls -l /app/src
RUN echo "---- Listing /app/src/peoples_coin directory ----" && ls -l /app/src/peoples_coin
RUN echo "---- PYTHONPATH environment variable ----" && echo $PYTHONPATH
RUN python3 -c "import sys; print('sys.path:', sys.path); import peoples_coin.factory; print('Imported peoples_coin.factory successfully')"

# Switch to non-root user
USER appuser

# Expose default Cloud Run port
EXPOSE 8080

# Start the app using Gunicorn and Flask factory pattern
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]

