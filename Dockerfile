# Use official lightweight Python Alpine image
FROM python:3.9-alpine

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set working dir
WORKDIR /app

# Install build/runtime deps
RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    bash \
    gcc \
    musl-dev \
    linux-headers

# Copy requirements & install
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the actual source code
COPY src/ src/

# Fix ownership
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.run:app"]

