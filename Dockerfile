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
RUN pip install Flask-Cors==4.0.0 # <<< THIS LINE IS THE ONE THAT HAD THE TYPO - ENSURE 'RUN pip' IS CORRECT

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
# TEMPORARY DIAGNOSTIC CMD: This will just print a message and sleep.
# It will confirm if the container and Python interpreter are starting.
CMD ["python", "-c", "import os; print('Container starting up! PORT:', os.environ.get('PORT', 'N/A'), flush=True); import time; time.sleep(30); print('Container finished sleeping.', flush=True);"]

# REMEMBER TO CHANGE THIS BACK TO YOUR ORIGINAL GUNICORN CMD AFTER DIAGNOSIS!
# Original CMD was likely: CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]

# Metadata labels (usually automatically added by Cloud Build)
LABEL google.build_id=$BUILD_ID
LABEL google.source=$SOURCE_LOCATION
