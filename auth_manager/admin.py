import sys
import os
# Ensure parent package is in path for standalone runs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from auth_manager.models import db, User
from functools import wraps

admin_bp = Blueprint('admin', __name__, template_folder='templates')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/admin/users')
@login_required
@admin_required
def list_users():
    users_ref = db.collection('users').stream()
    users = []
    for doc in users_ref:
        users.append(doc.to_dict() | {'id': doc.id})
    return render_template('auth_manager/users.html', users=users)

@admin_bp.route('/admin/users/approve/<user_id>', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    user = User.get(user_id)
    if user:
        user.is_approved = True
        user.save()
        flash(f'User {user.username} approved', 'success')
    return redirect(url_for('admin.list_users'))

@admin_bp.route('/admin/users/revoke/<user_id>', methods=['POST'])
@login_required
@admin_required
def revoke_user(user_id):
    if user_id == current_user.id:
        flash('You cannot revoke your own access', 'error')
    else:
        user = User.get(user_id)
        if user:
            user.is_approved = False
            user.save()
            flash(f'Access revoked for {user.username}', 'success')
    return redirect(url_for('admin.list_users'))

@admin_bp.route('/admin/users/toggle_admin/<user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    if user_id == current_user.id:
        flash('You cannot change your own admin status', 'error')
    else:
        user = User.get(user_id)
        if user:
            user.is_admin = not user.is_admin
            user.save()
            flash(f'Admin status toggled for {user.username}', 'success')
    return redirect(url_for('admin.list_users'))

@admin_bp.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = 'is_admin' in request.form
        is_approved = 'is_approved' in request.form
        
        if User.get_by_email(email):
            flash('Email already registered', 'error')
        else:
            User.create_user(username, email, password, is_approved=is_approved, is_admin=is_admin)
            flash(f'User {username} created successfully', 'success')
            return redirect(url_for('admin.list_users'))
            
    return render_template('auth_manager/add_edit_user.html', user=None)

@admin_bp.route('/admin/users/edit/<user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.get(user_id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin.list_users'))
        
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.is_admin = 'is_admin' in request.form
        user.is_approved = 'is_approved' in request.form
        user.save()
        flash(f'User {user.username} updated', 'success')
        return redirect(url_for('admin.list_users'))
        
    return render_template('auth_manager/add_edit_user.html', user=user)

@admin_bp.route('/admin/users/delete/<user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash('You cannot delete your own account', 'error')
    else:
        user = User.get(user_id)
        if user:
            user.delete()
            flash(f'User {user.username} deleted', 'success')
    return redirect(url_for('admin.list_users'))

@admin_bp.route('/admin/users/reset_password/<user_id>', methods=['POST'])
@login_required
@admin_required
def reset_password_admin(user_id):
    new_password = request.form.get('new_password')
    user = User.get(user_id)
    if user:
        if user.auth_provider != 'local':
            flash('Cannot reset password for Google users', 'error')
        else:
            user.update_password(new_password)
            flash(f'Password reset for {user.username}', 'success')
    return redirect(url_for('admin.list_users'))
