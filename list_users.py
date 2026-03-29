from google.cloud import firestore
db = firestore.Client(database='checklist')
print("--- USERS ---")
for u in db.collection('users').stream():
    data = u.to_dict()
    print(f"ID: {u.id} | Email: {data.get('email')} | Approved: {data.get('is_approved')} | Admin: {data.get('is_admin')}")
