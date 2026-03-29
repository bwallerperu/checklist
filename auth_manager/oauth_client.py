import sys
import os
# Ensure parent package is in path for standalone runs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from authlib.integrations.flask_client import OAuth
import os

oauth = OAuth()

def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
