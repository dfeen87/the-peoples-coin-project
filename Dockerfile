# Use a modern Python base image
FROM python:3.11-slim

# Unique identifier for build version
LABEL build_version="20250726.15-google-final"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src

# Create non-root user and group
RUN groupadd --system appgroup && useradd --system --create-home --home-dir /app --shell /bin/bash --gid appgroup appuser

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy dependencies file and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy entire project into the image
COPY . .

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Use non-root user
USER appuser

# Expose port for Cloud Run
EXPOSE 8080

# Start Gunicorn with the correct module path
CMD ["gunicorn", "peoples_coin.wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

