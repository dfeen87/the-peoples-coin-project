# Use Python base image
FROM python:3.9-slim

# Set working directory inside the container
WORKDIR /app

# Copy only requirements first to leverage Docker cache for dependencies
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the app source code
COPY . .

# Set environment variables
ENV PYTHONPATH=src
ENV FLASK_ENV=production

# Expose the port your app runs on
EXPOSE 5000

# Run your app
CMD ["python", "-m", "peoples_coin.run"]

