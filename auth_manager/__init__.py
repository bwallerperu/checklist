from flask_login import LoginManager
from auth_manager.models import User
from auth_manager.core import auth_bp, approved_only
from auth_manager.admin import admin_bp
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the project root
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = None
login_manager.login_message_category = 'error'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def init_auth(app):
    """
    Convenience function to register all auth components to a Flask app.
    """
    # Configure app secret key with fallback
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        # Fallback for development if .env is missing/unreadable
        secret_key = 'dev-secret-key-replace-this-in-production'
        print("WARNING: SECRET_KEY not found in environment. Using development fallback.")
    
    app.secret_key = secret_key

    # Initialize extensions
    login_manager.init_app(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
