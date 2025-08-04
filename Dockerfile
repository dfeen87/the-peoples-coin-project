# Use a slim Python image
FROM python:3.11-slim

# Install system dependencies needed to build some Python packages
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Explicitly copy ONLY the necessary files and folders
COPY requirements.txt .
COPY wsgi.py .
COPY peoples_coin/ ./peoples_coin/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "wsgi:app"]
