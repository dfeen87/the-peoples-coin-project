# Use a slim Python image
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your project files (including your entrypoint.sh)
COPY . .

# Make your entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Expose the port (Cloud Run will provide the $PORT variable)
EXPOSE 8080

# Set the entrypoint script as the startup command for the container
ENTRYPOINT ["/app/entrypoint.sh"]
