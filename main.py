import os
import time
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.exceptions import HTTPException
from google.cloud import firestore
from google.api_core import exceptions as google_exceptions
from flask_login import login_required, current_user, logout_user
from auth_manager import init_auth, approved_only
from auth_manager.models import sanitize_for_session

app = Flask(__name__)

# Make enumerate available in templates
app.jinja_env.globals.update(enumerate=enumerate)

# Initialize Authentication Module
init_auth(app)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Error Handlers
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal Server Error: {error}", exc_info=True)
    return render_template('error.html', 
                           error_title="Error Interno del Servidor",
                           error_message="Lo sentimos, algo salió mal en nuestros servidores. Ya hemos sido notificados."), 500

@app.errorhandler(google_exceptions.ServiceUnavailable)
def handle_service_unavailable(error):
    logger.warning(f"Service Unavailable (Firestore): {error}")
    return render_template('error.html', 
                           error_title="Servicio Temporalmente No Disponible",
                           error_message="La base de datos está experimentando una carga inusual. Por favor, intente refrescar la página."), 503

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through Flask/Werkzeug HTTP errors (like 404, 401)
    if isinstance(e, HTTPException):
        return e
    
    logger.error(f"Unhandled Exception: {e}", exc_info=True)
    return render_template('error.html', 
                           error_title="Error Inesperado",
                           error_message="Ha ocurrido un error inesperado. Por favor, intente de nuevo en unos momentos."), 500

# Initialize Firestore
# Note: authentication is handled automatically by Google Cloud Run (and ADC locally)
db = firestore.Client(database='checklist')

# In-memory cache for company configuration to reduce Firestore reads (10 min TTL)
_company_config_cache = {'data': {}, 'timestamp': 0}
_CACHE_TTL_SECONDS = 600

@app.context_processor
def inject_company_config():
    """Inject company configuration into all templates with session-level caching."""
    # Check if config is already in session
    if 'company_config' in session:
        return {'company_config': session['company_config']}
        
    try:
        config_doc = db.collection('company_config').document('settings').get()
        if config_doc.exists:
            config_data = config_doc.to_dict()
            # Security/Stability: Ensure data is serializable before saving to session.
            # Firestore timestamps are datetime objects which crash Flask session serialization.
            clean_config = sanitize_for_session(config_data)
            session['company_config'] = clean_config
            return {'company_config': clean_config}
    except Exception as e:
        logger.error(f"Error fetching company config: {e}")
            
    return {'company_config': {}}

@app.route('/')
def root():
    """Always force login when starting the app by logging out any active session."""
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for('auth.login'))

@app.route('/catalog')
@login_required
@approved_only
def catalog():
    # Fetch checklists with access control
    checklists_ref = db.collection('checklist_configs')
    
    # If not admin, filter by assigned_to or is_public
    if not current_user.is_admin:
        # Standard users see:
        # 1. Checklists explicitly assigned to them
        # 2. Checklists marked as is_public: True
        # Note: Firestore 'OR' queries on arrays can be complex, 
        # so we fetch and filter to ensure maximum precision.
        all_checklists_ref = checklists_ref.limit(300).stream()
        checklist_list = []
        for doc in all_checklists_ref:
            data = doc.to_dict()
            is_assigned = current_user.username in data.get('assigned_to', [])
            is_public = data.get('is_public', False)
            if is_assigned or is_public:
                checklist_list.append(data | {'id': doc.id})
    else:
        # Admins see everything
        checklists = checklists_ref.limit(300).stream()
        checklist_list = []
        for doc in checklists:
            checklist_list.append(doc.to_dict() | {'id': doc.id})

    return render_template('index.html', checklists=checklist_list)

@app.route('/create', methods=['GET', 'POST'])
@login_required
@approved_only
def create():
    """Create a new checklist."""
    if request.method == 'POST':
        title = request.form.get('title')
        steps_descriptions = request.form.getlist('step_description')
        steps_types = request.form.getlist('step_type')
        
        steps = []
        for desc, type_ in zip(steps_descriptions, steps_types):
            if desc.strip(): # Only add non-empty steps
                steps.append({'description': desc, 'type': type_})
        
        if title and steps:
            db.collection('checklist_configs').add({
                'title': title,
                'steps': steps,
                'icon': request.form.get('icon', 'clipboard'),
                'is_public': request.form.get('is_public') == 'on',
                'assigned_to': request.form.getlist('assigned_to'),
                'created_at': firestore.SERVER_TIMESTAMP,
                'created_by': current_user.username
            })
            flash(f'Checklist "{title}" creado correctamente.', 'success')
            return redirect(url_for('catalog'))
        else:
            flash('Error: El título y al menos un paso son obligatorios.', 'error')
            
    # Fetch all approved users for the assignment list
    users_ref = db.collection('users').where('is_approved', '==', True).stream()
    users = [u.to_dict().get('username') for u in users_ref if u.to_dict().get('username')]
    return render_template('create.html', users=sorted(users))

@app.route('/checklist/<id>')
@login_required
@approved_only
def view_checklist(id):
    """View and execute a checklist."""
    doc = db.collection('checklist_configs').document(id).get()
    if not doc.exists:
        return "Checklist not found", 404
        
    checklist = doc.to_dict() | {'id': doc.id}
    return render_template('checklist.html', checklist=checklist)

@app.route('/submit/<id>', methods=['POST'])
@login_required
@approved_only
def submit(id):
    """Submit checklist results."""
    # Fetch the original configuration to snapshot it
    config_ref = db.collection('checklist_configs').document(id)
    config_doc = config_ref.get()
    
    if not config_doc.exists:
        return "Checklist not found", 404
        
    config_data = config_doc.to_dict()
    
    # Collect responses based on original configuration
    responses = {}
    for i, step in enumerate(config_data.get('steps', [])):
        field_name = f'step_{i}'
        if step.get('type') == 'boolean':
            # Checkbox values are only present if checked
            responses[str(i)] = 'Sí' if request.form.get(field_name) == 'on' else 'No'
        else:
            responses[str(i)] = request.form.get(field_name, '')
            
    # Save result
    result_data = {
        'checklist_id': id,
        'checklist_snapshot': config_data,
        'responses': responses,
        'deployed_at': firestore.SERVER_TIMESTAMP,
        'deployed_by': current_user.username
    }
    
    db.collection('checklist_results').add(result_data)
    
    return redirect(url_for('catalog'))

@app.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@approved_only
def edit_checklist(id):
    """Edit an existing checklist."""
    doc_ref = db.collection('checklist_configs').document(id)
    doc = doc_ref.get()
    if not doc.exists:
        return "Checklist not found", 404
        
    if request.method == 'POST':
        title = request.form.get('title')
        steps_descriptions = request.form.getlist('step_description')
        steps_types = request.form.getlist('step_type')
        
        steps = []
        for desc, type_ in zip(steps_descriptions, steps_types):
            if desc.strip():
                steps.append({'description': desc, 'type': type_})
        
        if title and steps:
            doc_ref.update({
                'title': title,
                'steps': steps,
                'icon': request.form.get('icon', 'clipboard'),
                'is_public': request.form.get('is_public') == 'on',
                'assigned_to': request.form.getlist('assigned_to'),
                'updated_at': firestore.SERVER_TIMESTAMP,
                'updated_by': current_user.username
            })
            flash(f'Checklist "{title}" actualizado correctamente.', 'success')
            return redirect(url_for('catalog'))
        else:
            flash('Error: El título y al menos un paso son obligatorios.', 'error')
            
    # Fetch all approved users for the assignment list
    users_ref = db.collection('users').where('is_approved', '==', True).stream()
    all_users = [u.to_dict().get('username') for u in users_ref if u.to_dict().get('username')]
    
    checklist = doc.to_dict() | {'id': doc.id}
    return render_template('edit.html', checklist=checklist, users=sorted(all_users))

@app.route('/delete/<id>', methods=['POST'])
@login_required
@approved_only
def delete_checklist(id):
    """Delete a checklist."""
    db.collection('checklist_configs').document(id).delete()
    return redirect(url_for('catalog'))


if __name__ == "__main__":
    # Local development
    # Use 0.0.0.0 for Docker/external accessibility
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
