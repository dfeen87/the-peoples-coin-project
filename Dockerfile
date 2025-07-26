FROM python:3.11-slim

LABEL build_version="20250726.15-install-sudo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/src

# Create non-root user 'appuser' and group 'appgroup'
RUN groupadd --system appgroup && useradd --system -g appgroup -d /src -s /bin/bash appuser

WORKDIR /src

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash \
    sudo && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r /requirements.txt

COPY src/ .

# Copy Firebase credentials file (make sure this file is next to your Dockerfile or adjust path)
COPY firebase-admin-sdk-key.json /app/firebase-admin-sdk-key.json

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Fix ownership of the source and the credentials file to the non-root user
RUN chown -R appuser:appgroup /src /app/firebase-admin-sdk-key.json

USER appuser

EXPOSE 8080

# Uncomment and use this if you have an entrypoint script that needs to run
# ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "--chdir", "peoples_coin", "wsgi:app", "--bind", "0.0.0.0:8080"]

