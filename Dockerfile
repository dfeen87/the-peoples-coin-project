# Use a slim Python 3.11 base image
FROM python:3.11-slim

# Install build dependencies (if needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire source code
COPY src/ /app/src/

# Set PYTHONPATH so Python can find your code
ENV PYTHONPATH=/app/src

# Optional: Run Python in unbuffered mode for better logging
ENV PYTHONUNBUFFERED=1

# Expose port 8080 for Cloud Run or other hosts
EXPOSE 8080

# Use a non-root user for security (optional but recommended)
RUN useradd -m appuser
USER appuser

# Start the Gunicorn server binding to 0.0.0.0 and specified port
CMD ["sh", "-c", "gunicorn peoples_coin.app:app --bind 0.0.0.0:${PORT:-8080}"]

