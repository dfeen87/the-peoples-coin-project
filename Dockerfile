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

# In your Dockerfile (near the very end)

# CRITICAL DIAGNOSTIC CMD: This will force application startup errors to logs.
# It attempts to import your Flask app directly and prints any exceptions.
CMD ["bash", "-c", " \
  echo '--- CONTAINER STARTING UP ---' && \
  export PYTHONUNBUFFERED=1 && \
  python -c ' \
    import sys; \
    import traceback; \
    try: \
      from peoples_coin.wsgi import app; \
      print(\"--- Flask APP IMPORTED SUCCESSFULLY ---\", flush=True); \
      # Keep container alive if successful for inspection (e.g., if you want to SSH into it)
      import time; time.sleep(300); \
    except Exception as e: \
      print(f\"--- ERROR DURING APP IMPORT/STARTUP ---: {e}\", file=sys.stderr); \
      traceback.print_exc(file=sys.stderr); \
      sys.exit(1); \
  ' \
"]

# REMEMBER TO CHANGE THIS CMD BACK TO YOUR ORIGINAL GUNICORN CMD AFTER DIAGNOSIS!
# Original CMD was: CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "peoples_coin.wsgi:app"]
# Metadata labels (usually automatically added by Cloud Build)
LABEL google.build_id=$BUILD_ID
LABEL google.source=$SOURCE_LOCATION
