FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install first
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy src folder (with your peoples_coin package inside it)
COPY src/ ./src/

# Set PYTHONPATH so Python can find your package under src
ENV PYTHONPATH=/app/src

EXPOSE 8080

# Use the PORT env var injected by Cloud Run to bind gunicorn
CMD ["sh", "-c", "gunicorn src.peoples_coin.app:app --bind 0.0.0.0:${PORT:-8080}"]

