ROM python:3.11-slim # <<< CRITICAL CHANGE: Revert to slim

# --- Unique Identifier ---
LABEL build_version="20250726.8-slim-final" # <<< UPDATE THIS LABEL
# ---

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app # <<< Ensure this is still /app for --chdir

# Create a non-root user and group for enhanced security
# Revert useradd/groupadd commands for Debian-based 'slim' image
RUN groupadd --system appgroup && useradd --system -g appgroup -d /app -s /bin/bash appuser # <<< CRITICAL CHANGE

WORKDIR /app

# Revert apt-get commands for Debian-based 'slim' image
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# Copy entrypoint.sh (if still present, though not used by CMD)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

CMD ["gunicorn", "--chdir", "src/peoples_coin", "wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

