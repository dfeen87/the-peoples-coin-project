import sys
import os

# Add the 'src' directory to sys.path so 'peoples_coin' module can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from peoples_coin import create_app, db
from flask_migrate import Migrate
from flask.cli import FlaskGroup

app = create_app()
migrate = Migrate(app, db)
cli = FlaskGroup(app)

if __name__ == '__main__':
    cli()

