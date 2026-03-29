from google.cloud import firestore
from werkzeug.security import generate_password_hash

# IMPORTANT: Ensure the database name matches the app's configuration
db = firestore.Client(database='checklist')
users_ref = db.collection('users')

print("Starting FULL collection reset...")
# 1. DELETE ALL USERS
docs = users_ref.stream()
count = 0
for doc in docs:
    doc.reference.delete()
    count += 1
print(f"Purged {count} documents.")

# 2. CREATE MASTER ADMIN
master_admin_email = "admin@test.com"
master_admin_password = "password123"
hashed_password = generate_password_hash(master_admin_password)

new_user_data = {
    'username': 'Administrador',
    'email': master_admin_email,
    'password': hashed_password,
    'auth_provider': 'local',
    'is_approved': True,
    'is_admin': True,
    'created_at': firestore.SERVER_TIMESTAMP
}

# Add with a predictable ID to ease debugging
users_ref.document('master_admin').set(new_user_data)

print(f"--- RESET COMPLETE ---")
print(f"Single User Created:")
print(f"Email: {master_admin_email}")
print(f"Pass: {master_admin_password}")
print(f"ID: master_admin")
