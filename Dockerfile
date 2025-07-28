# Use a slim Python 3.11 base image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your source code
COPY src/ ./src/

# Make sure Python knows where to find your code
ENV PYTHONPATH=/app/src

# Expose the port for Cloud Run
EXPOSE 8080

# Start your app with gunicorn
CMD ["sh", "-c", "gunicorn peoples_coin.app:app --bind 0.0.0.0:${PORT:-8080}"]

