FROM python:3.11-slim

LABEL build_version="20250726.15-install-sudo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/src

# Create non-root user 'appuser' and group 'appgroup'
RUN groupadd --system appgroup && useradd --system -g appgroup -d /src -s /bin/bash appuser

WORKDIR /src

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash \
    sudo && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r /requirements.txt

# Copy application code
COPY src/ .

# Optional entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Fix permissions for non-root user
RUN chown -R appuser:appgroup /src

USER appuser

EXPOSE 8080

# Use the entrypoint script if needed
# ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "peoples_coin:create_app()"]

