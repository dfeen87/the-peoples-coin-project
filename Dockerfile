# Use a slim Python 3.11 base image
FROM python:3.11-slim

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY src/ /app/src/

# Make sure Python can find peoples_coin inside src
ENV PYTHONPATH=/app/src

# Unbuffered logging
ENV PYTHONUNBUFFERED=1

# Cloud Run port
ENV PORT=8080

# Add a non-root user
RUN useradd -m appuser
USER appuser

# 🔹 Force gunicorn to use /app/src as working directory so it finds peoples_coin
CMD ["gunicorn", "--chdir", "/app/src", "peoples_coin.wsgi:app", "--bind", "0.0.0.0:${PORT}"]

