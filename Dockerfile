FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project into the image
COPY . .

# Ensure Python can find the src/ directory for imports like `from peoples_coin import create_app`
ENV PYTHONPATH=/app/src
ENV PORT=8080

# Run the app with Gunicorn, binding to the Cloud Run-required port
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "wsgi:app"]

