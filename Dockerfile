# Use a slim Python image
FROM python:3.11-slim

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
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

# Expose the port Cloud Run will use
EXPOSE 8080

# Set environment variables for Flask (optional but nice for debugging)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run the application with Gunicorn
#  - Use 'exec' form for proper signal handling
#  - Bind to Cloud Run's $PORT (default 8080)
#  - Allow threads for better concurrency on small containers
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "8", "wsgi:app"]


