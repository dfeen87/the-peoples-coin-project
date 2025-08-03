# Use a slim Python image
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy requirements file first to leverage Docker's layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project code from your current directory into /app
# The .dockerignore file will correctly exclude venv, etc.
COPY . .

# Expose the port the application will run on
EXPOSE 8080

# The command to run your application, now with the correct path
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--chdir", "peoples-coin", "peoples_coin.wsgi:app"]
