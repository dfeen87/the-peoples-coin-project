# Use official lightweight Python Alpine image
FROM python:3.9-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

# Create non-root user and group
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set working directory
WORKDIR /app

# Install build and runtime dependencies
RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    bash \
    gcc \
    musl-dev \
    linux-headers

# Copy dependency specs first for caching
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Fix permissions for non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port 8080 (for Cloud Run or Kubernetes)
EXPOSE 8080

# Run Gunicorn server with 4 workers binding to all interfaces
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.run:app"]

