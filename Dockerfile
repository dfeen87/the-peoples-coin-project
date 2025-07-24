# Dockerfile

# Use the official Python image as a base
FROM python:3.9-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src

# Create a non-root user and group
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set the working directory in the container
WORKDIR /app

# Install build dependencies
RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    bash \
    gcc \
    musl-dev \
    linux-headers

# Copy requirements.txt into the container
COPY requirements.txt .

# Temporarily install Flask-Cors explicitly (diagnostic step - will remove later if successful)
RUN pip install Flask-Cors==4.0.0 # <<< This line

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY src/ src/

# Set correct ownership for the /app directory
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the port your Flask app will listen on
EXPOSE 8080

# Command to run the application using Gunicorn
# CRITICAL FIX: Change CMD back to Gunicorn to start the web server
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]

# REMEMBER TO REMOVE THE TEMPORARY Flask-Cors INSTALL LINE (RUN pip install Flask-Cors==4.0.0) AFTER THIS WORKS!
# It's better to keep requirements.txt as the single source for dependencies.

# Metadata labels (usually automatically added by Cloud Build)
LABEL google.build_id=$BUILD_ID
LABEL google.source=$SOURCE_LOCATION
