from flask_login import LoginManager
from auth_manager.models import User
from auth_manager.core import auth_bp, approved_only
from auth_manager.admin import admin_bp
from auth_manager.oauth_client import init_oauth
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
    # Configure app
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-it')
    
    # Initialize extensions
    login_manager.init_app(app)
    init_oauth(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
