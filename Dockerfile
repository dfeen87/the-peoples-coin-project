# Use a modern Python base image
FROM python:3.11-slim

# Metadata label
LABEL build_version="20250726.13-ultra-copy-fix"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/src

# Create non-root user and group
RUN groupadd --system appgroup && useradd --system -g appgroup -d /src -s /bin/bash appuser

# Set working directory
WORKDIR /src

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY src/peoples_coin/ ./peoples_coin/
COPY src/peoples_coin/wsgi.py ./peoples_coin/wsgi.py

# Optional: Copy entrypoint if you use it
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Change ownership
RUN chown -R appuser:appgroup /src

# Run as non-root user
USER appuser

EXPOSE 8080

# Gunicorn command
CMD ["gunicorn", "--chdir", "peoples_coin", "wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

