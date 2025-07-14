# Use Python base image
FROM python:3.9-slim

# Set working directory inside the container
WORKDIR /app

# Copy all project files into the container
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONPATH=src
ENV FLASK_ENV=production

# Expose the port your app runs on
EXPOSE 5000

# Run your app
CMD ["python", "-m", "peoples_coin.run"]

