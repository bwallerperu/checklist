import sys
import os
# Ensure parent package is in path for standalone runs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from auth_manager.models import User
from auth_manager.oauth_client import oauth
from functools import wraps

auth_bp = Blueprint('auth', __name__, template_folder='templates')

def approved_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_approved:
            return redirect(url_for('auth.pending'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.get_by_email(email)
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
            
    return render_template('auth_manager/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.get_by_email(email):
            flash('Email already registered', 'error')
        else:
            User.create_user(username, email, password, auth_provider='local')
            flash('Registration successful! Please wait for admin approval.', 'success')
            return redirect(url_for('auth.login'))
            
    return render_template('auth_manager/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/pending')
@login_required
def pending():
    if current_user.is_approved:
        return redirect(url_for('index'))
    return render_template('auth_manager/pending.html')

# Google OAuth Routes
@auth_bp.route('/login/google')
def google_auth():
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/login/google/callback')
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info:
        flash('Failed to fetch user info from Google', 'error')
        return redirect(url_for('auth.login'))
    
    email = user_info['email']
    user = User.get_by_email(email)
    
    if not user:
        # Create new Google user
        username = user_info.get('name', email.split('@')[0])
        user = User.create_user(username, email, auth_provider='google')
        flash('Account created with Google! Please wait for admin approval.', 'success')
    
    login_user(user)
    return redirect(url_for('index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 1. Update Username (Allowed for all)
        if new_username and new_username != current_user.username:
            current_user.update_username(new_username)
            flash('Nombre de usuario actualizado', 'success')
            
        # 2. Update Password (Only for local users)
        if new_password:
            if current_user.auth_provider != 'local':
                flash('La gestión de contraseñas es externa para cuentas de Google', 'error')
            elif new_password != confirm_password:
                flash('Las contraseñas no coinciden', 'error')
            elif len(new_password) < 8:
                flash('La contraseña debe tener al menos 8 caracteres', 'error')
            else:
                current_user.update_password(new_password)
                flash('Contraseña actualizada con éxito', 'success')
                
    return render_template('auth_manager/profile.html')
