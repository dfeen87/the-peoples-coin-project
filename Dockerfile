# Use a slim Python image
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Explicitly copy only the necessary files
COPY requirements.txt .
COPY wsgi.py .
COPY peoples_coin/ ./peoples_coin/
# If alembic is needed for runtime, uncomment the next line
# COPY alembic/ ./alembic/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "wsgi:app"]
