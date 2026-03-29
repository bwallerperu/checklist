import os
from flask import Flask, render_template, request, redirect, url_for
from google.cloud import firestore
from flask_login import login_required, current_user
from auth_manager import init_auth, approved_only

app = Flask(__name__)

# Initialize Authentication Module
init_auth(app)

# Initialize Firestore
# Note: authentication is handled automatically by Google Cloud Run (and ADC locally)
db = firestore.Client(database='checklist')

@app.route('/')
@login_required
@approved_only
def index():
    """Catalog of all checklists."""
    # Placeholder for fetching checklists from Firestore
    checklists_ref = db.collection('checklist_configs')
    checklists = checklists_ref.stream()
    
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
                'created_at': firestore.SERVER_TIMESTAMP,
                'created_by': current_user.username
            })
            return redirect(url_for('index'))
            
    return render_template('create.html')

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
    
    return redirect(url_for('index'))

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
                'updated_at': firestore.SERVER_TIMESTAMP,
                'updated_by': current_user.username
            })
            return redirect(url_for('index'))
            
    checklist = doc.to_dict() | {'id': doc.id}
    return render_template('edit.html', checklist=checklist)

@app.route('/delete/<id>', methods=['POST'])
@login_required
@approved_only
def delete_checklist(id):
    """Delete a checklist."""
    db.collection('checklist_configs').document(id).delete()
    return redirect(url_for('index'))

if __name__ == "__main__":
    # Local development
    # Use 0.0.0.0 for Docker/external accessibility
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
