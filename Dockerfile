FROM python:3.11-slim

LABEL build_version="20250726.13-final-alignment"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/src

RUN groupadd --system appgroup && useradd --system -g appgroup -d /src -s /bin/bash appuser

WORKDIR /src

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    bash && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r /requirements.txt

COPY src/ .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN chown -R appuser:appgroup /src

USER appuser

EXPOSE 8080

CMD ["gunicorn", "peoples_coin.wsgi:app", "--bind", "0.0.0.0:8080", "--workers=1", "--timeout=300"]

