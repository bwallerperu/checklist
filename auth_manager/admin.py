import sys
import os
# Ensure parent package is in path for standalone runs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from google.cloud import firestore
from auth_manager.models import db, User, sanitize_for_session
from functools import wraps

admin_bp = Blueprint('admin', __name__, template_folder='templates')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('catalog'))
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
        
        # Handle password reset if provided
        new_password = request.form.get('password')
        if new_password:
            if user.auth_provider != 'local':
                flash('Cannot reset password for external provider users (e.g. Google)', 'error')
            else:
                user.update_password(new_password)
                flash('Password updated successfully', 'success')

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

@admin_bp.route('/admin/company', methods=['GET', 'POST'])
@login_required
@admin_required
def company_settings():
    config_ref = db.collection('company_config').document('settings')
    
    if request.method == 'POST':
        config_data = {
            'name': request.form.get('name'),
            'address': request.form.get('address'),
            'phone': request.form.get('phone'),
            'email': request.form.get('email'),
            'footer_text': request.form.get('footer_text'),
            'updated_at': firestore.SERVER_TIMESTAMP,
            'updated_by': current_user.username
        }
        config_ref.set(config_data, merge=True)
        
        # Security/Stability: Ensure data is serializable before saving to session.
        # This prevents the application from crashing when trying to save the session.
        session['company_config'] = sanitize_for_session(config_data)
        
        flash('Configuración de la empresa actualizada', 'success')
        return redirect(url_for('admin.company_settings'))
        
    config_doc = config_ref.get()
    config = config_doc.to_dict() if config_doc.exists else {}
    
    return render_template('auth_manager/company_settings.html', config=config)

@admin_bp.route('/admin/results')
@login_required
def list_results():
    if current_user.is_admin:
        # Admins see everything - Use native sorting for performance
        results_ref = db.collection('checklist_results')\
            .order_by('deployed_at', direction=firestore.Query.DESCENDING)\
            .limit(100)\
            .stream()
    else:
        # Standard users only see their own results
        # NOTE: We remove .order_by() on the server side because combining it with 
        # .where() requires a composite index. We sort in Python below instead.
        results_ref = db.collection('checklist_results')\
            .where('deployed_by', '==', current_user.username)\
            .limit(100)\
            .stream()
            
    results = []
    unique_titles = set()
    unique_users = set()
    for doc in results_ref:
        data = doc.to_dict() | {'id': doc.id}
        results.append(data)
        if 'checklist_snapshot' in data and 'title' in data['checklist_snapshot']:
            unique_titles.add(data['checklist_snapshot']['title'])
        if 'deployed_by' in data:
            unique_users.add(data['deployed_by'])

    # Apply manual sort for non-admins (or everyone for consistency)
    results = sorted(results, key=lambda x: x.get('deployed_at') or 0, reverse=True)
            
    return render_template('auth_manager/results.html', 
                           results=results, 
                           unique_titles=sorted(list(unique_titles)),
                           unique_users=sorted(list(unique_users)))

@admin_bp.route('/admin/results/<result_id>')
@login_required
def view_result(result_id):
    doc = db.collection('checklist_results').document(result_id).get()
    if not doc.exists:
        flash('Resultado no encontrado', 'error')
        return redirect(url_for('admin.list_results'))
    
    result = doc.to_dict() | {'id': doc.id}
    
    # Security check: Standard users can only view their own results
    if not current_user.is_admin and result.get('deployed_by') != current_user.username:
        flash('No tiene permiso para ver este resultado', 'error')
        return redirect(url_for('admin.list_results'))
        
    return render_template('auth_manager/view_result.html', result=result)

@admin_bp.route('/admin/results/delete/<result_id>', methods=['POST'])
@login_required
@admin_required
def delete_result(result_id):
    db.collection('checklist_results').document(result_id).delete()
    flash('Resultado eliminado correctamente', 'success')
    return redirect(url_for('admin.list_results'))
