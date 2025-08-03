    #!/bin/bash
    # This script is the entrypoint for the Docker container.
    # It ensures the application starts correctly with Gunicorn.

    echo "--- Starting entrypoint.sh ---" >&2
    echo "PYTHONPATH: $PYTHONPATH" >&2
    echo "PORT: $PORT" >&2

    # Execute Gunicorn to run the Flask application
    # 'wsgi:app' refers to the 'app' callable in the 'wsgi.py' module
    # -w 4: 4 worker processes
    # -b 0.0.0.0:$PORT: Bind to all interfaces on the port provided by Cloud Run
    python -m gunicorn -w 4 -b 0.0.0.0:$PORT peoples_coin.wsgi:app

    echo "--- Gunicorn exited ---" >&2

