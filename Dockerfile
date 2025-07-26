# Use a modern Python base image
FROM python:3.11-alpine

# --- Unique Identifier ---
LABEL build_version="20250726.6-single-worker" # <<< UPDATED LABEL
# ---

# Set environment variables for Python and Flask application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    # Adjust PYTHONPATH to include /app (root of WORKDIR)
    # Gunicorn will change directory to /app/src/peoples_coin,
    # so Python needs to find 'peoples_coin' package relative to /app.
    PYTHONPATH=/app # <<< CRITICAL CHANGE for --chdir

# Create a non-root user and group for enhanced security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup -D -h /app -s /bin/bash appuser

WORKDIR /app

RUN apk update && apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    postgresql-dev \
    bash && \
    rm -rf /var/cache/apk/*

COPY requirements.txt .

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# Copy entrypoint.sh (if you still have it, though no longer used with this CMD)
# If you removed entrypoint.sh, you can remove these lines.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

# --- MODIFIED CMD: Single Worker, Chdir, and Timeout ---
# This is the most promising fix for startup issues.
CMD ["gunicorn", "--chdir", "src/peoples_coin", "wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

