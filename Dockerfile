# Use a slim Python image
FROM python:3.11-slim

# Install system dependencies needed for building Python packages and netcat (for testing if needed)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy only requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY wsgi.py ./
COPY peoples_coin/ ./peoples_coin/

# Copy the Firebase service account JSON key
COPY peoples_coin/heroic-tide-428421-q7-9ff07058342c.json /app/peoples_coin/heroic-tide-428421-q7-9ff07058342c.json

# Expose the port Cloud Run will use
EXPOSE 8080

# Set environment variables for Flask (optional but helpful)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run the application with Gunicorn, adjusted timeout higher (e.g. 60s) for safety
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "--timeout", "60", "--preload", "wsgi:app"]

