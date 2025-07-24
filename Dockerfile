# Dockerfile

# Change base image from alpine to slim-buster for better compatibility
FROM python:3.9-slim-buster # <<< This line must be exactly as is, without extra characters or comments on it

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app/src

# Create a non-root user and group (Debian/Ubuntu specific syntax for system users)
RUN groupadd --system appgroup && useradd --system -g appgroup -d /app -s /bin/bash appuser

# Set the working directory in the container
WORKDIR /app

# Install build dependencies (using apt for Debian-based image)
# These are essential for compiling some Python packages like psycopg2, cryptography.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \ # Needed for psycopg2-binary to connect to PostgreSQL
    bash \
    # Clean up apt caches to reduce image size
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt into the container
COPY requirements.txt .

# Temporarily install Flask-Cors explicitly (diagnostic step - will remove later if successful)
RUN pip install Flask-Cors==4.0.0

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

# ULTIMATE DIAGNOSTIC CMD: This will just print a message from bash and sleep.
# It will confirm if the container and bash shell are starting and outputting logs.
CMD ["bash", "-c", "echo '--- Bash is working (Buster)! ---' && sleep 30 && echo '--- Bash finished sleeping ---' && exit 0"]

# REMEMBER TO CHANGE THIS CMD BACK TO YOUR ORIGINAL GUNICORN CMD AFTER DIAGNOSIS!
# Original CMD was: CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]

# Metadata labels (usually automatically added by Cloud Build)
LABEL google.build_id=$BUILD_ID
LABEL google.source=$SOURCE_LOCATION
