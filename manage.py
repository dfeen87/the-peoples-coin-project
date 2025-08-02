import os
import sys
from flask.cli import FlaskGroup
from flask_migrate import Migrate

# This line adds your 'src' folder to the Python path
# so it can find your 'peoples_coin' code.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

# Now we can import your app from the peoples_coin module
from peoples_coin import create_app, db

app = create_app()
migrate = Migrate(app, db)
cli = FlaskGroup(app)

if __name__ == '__main__':
    cli()
