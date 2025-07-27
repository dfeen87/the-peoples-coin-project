# Use an official slim Python base image
FROM python:3.11-slim

# Set environment variables early for reliability
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app/src

# Set working directory
WORKDIR /app

# Install OS-level dependencies (if needed, e.g., for psycopg2 or SSL)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "wsgi:app"]

