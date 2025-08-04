# Use a slim Python image
FROM python:3.11-slim

# Install system dependencies needed to build some Python packages
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port
EXPOSE 8080

# The final command, now in shell form
CMD exec gunicorn --bind 0.0.0.0:8080 --workers 2 wsgi:app
