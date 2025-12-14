import os
import sys
import redis

def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(redis_url)
        pong = client.ping()
        if pong:
            print(f"Successfully connected to Redis at {redis_url}")
            sys.exit(0)
        else:
            print(f"Failed to ping Redis at {redis_url}")
            sys.exit(1)
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

