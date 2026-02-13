import os
from flask import Flask, render_template, request, redirect, url_for
from google.cloud import firestore

app = Flask(__name__)

# Initialize Firestore
# Note: authentication is handled automatically by Google Cloud Run (and ADC locally)
db = firestore.Client()

@app.route('/')
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
                # In a real app with auth, we'd add created_by here
                'created_by': 'anonymous' 
            })
            return redirect(url_for('index'))
            
    return render_template('create.html')

@app.route('/checklist/<id>')
def view_checklist(id):
    """View and execute a checklist."""
    doc = db.collection('checklist_configs').document(id).get()
    if not doc.exists:
        return "Checklist not found", 404
        
    checklist = doc.to_dict() | {'id': doc.id}
    return render_template('checklist.html', checklist=checklist)

@app.route('/submit/<id>', methods=['POST'])
def submit(id):
    """Submit checklist results."""
    # Fetch the original configuration to snapshot it
    config_ref = db.collection('checklist_configs').document(id)
    config_doc = config_ref.get()
    
    if not config_doc.exists:
        return "Checklist not found", 404
        
    config_data = config_doc.to_dict()
    
    # Collect responses
    responses = {}
    for key, value in request.form.items():
        if key.startswith('step_'):
            step_index = key.split('_')[1]
            responses[step_index] = value
            
    # Save result
    result_data = {
        'checklist_id': id,
        'checklist_snapshot': config_data,
        'responses': responses,
        'deployed_at': firestore.SERVER_TIMESTAMP,
        'deployed_by': 'anonymous' # Placeholder
    }
    
    db.collection('checklist_results').add(result_data)
    
    return redirect(url_for('index'))

if __name__ == "__main__":
    # Local development
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
