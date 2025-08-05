#!/bin/sh
set -e

echo "📦 Starting container for peoples-coin-service..."

# Wait for Cloud SQL connection
echo "⏳ Waiting for Cloud SQL to be ready..."
for i in $(seq 1 10); do
  if python - <<'EOF'
import os
from sqlalchemy import create_engine, text

try:
    from peoples_coin.models.init_db import get_database_url
    url = get_database_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✅ Database connection OK")
except Exception as e:
    print(f"⚠️ DB not ready: {e}")
    raise SystemExit(1)
EOF
  then
    break
  else
    echo "⏳ Retry DB connection in 3s..."
    sleep 3
  fi
done

# Run DB initialization
echo "🛠 Initializing database..."
python -m peoples_coin.models.init_db --verbose

echo "🚀 Starting Flask app..."
exec gunicorn --bind 0.0.0.0:8080 "peoples_coin.factory:create_app()"

