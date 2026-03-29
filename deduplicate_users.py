from google.cloud import firestore
from werkzeug.security import generate_password_hash

db = firestore.Client(database='checklist')
users_ref = db.collection('users')
users = users_ref.stream()

email_map = {}
to_delete = []

print("Analyzing users for duplicates...")
for doc in users:
    data = doc.to_dict()
    email = data.get('email')
    if not email:
        continue
        
    if email in email_map:
        # Keep the one with the most useful information or specific ID
        old_doc_id, old_data = email_map[email]
        
        # Heuristic: keep fixed IDs like 'admin_tester'
        if doc.id == 'admin_tester':
            to_delete.append(old_doc_id)
            email_map[email] = (doc.id, data)
        elif old_doc_id == 'admin_tester':
            to_delete.append(doc.id)
        else:
            # Keep the most recently updated/created if available, or just the first one
            to_delete.append(doc.id)
    else:
        email_map[email] = (doc.id, data)

print(f"Deleting {len(to_delete)} duplicate records...")
for doc_id in to_delete:
    users_ref.document(doc_id).delete()
    print(f"Deleted duplicate: {doc_id}")

# Guarantee admin account status for testing
admins = ['admin@test.com', 'admin_tester@example.com', 'bwaller@ddintl.com']
hashed_pw = generate_password_hash('password123')

for email in admins:
    if email in email_map:
        doc_id, _ = email_map[email]
        users_ref.document(doc_id).update({
            'password': hashed_pw,
            'is_approved': True,
            'is_admin': True
        })
        print(f"Verified/Reset Admin: {email} (ID: {doc_id})")

print("Cleanup complete.")
