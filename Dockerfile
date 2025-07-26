# Use a modern Python base image
FROM python:3.11-slim

# --- Unique Identifier ---
LABEL build_version="20250726.11-copy-src-fix"
# ---

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/src

# Set working directory to /src where your code will live
WORKDIR /src

# Create non-root user and group
RUN groupadd --system appgroup && useradd --system -g appgroup -d /src -s /bin/bash appuser

# Install system dependencies
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

# Copy the entire local 'src' directory (from build context) to /src in the container
COPY src/ .

# Copy entrypoint.sh (if still present)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set ownership of /src to the non-root user
RUN chown -R appuser:appgroup /src

# Switch to non-root user for running the app
USER appuser

# Expose the port your app listens on
EXPOSE 8080

# Run Gunicorn pointing to your app's wsgi.py inside peoples_coin package
CMD ["gunicorn", "--chdir", "peoples_coin", "wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

