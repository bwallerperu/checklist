import sys
import os
# Ensure parent package is in path for standalone runs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from google.cloud import firestore

# Initialize Firestore Client (assuming checklist database)
db = firestore.Client(database='checklist')

class User(UserMixin):
    def __init__(self, id, username, email, password=None, auth_provider='local', is_approved=False, is_admin=False, created_at=None):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.auth_provider = auth_provider
        self.is_approved = is_approved
        self.is_admin = is_admin
        self.created_at = created_at or firestore.SERVER_TIMESTAMP

    @staticmethod
    def get(user_id):
        if not user_id:
            return None
        doc = db.collection('users').document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            return User(
                id=doc.id,
                username=data.get('username'),
                email=data.get('email'),
                password=data.get('password'),
                auth_provider=data.get('auth_provider', 'local'),
                is_approved=data.get('is_approved', False),
                is_admin=data.get('is_admin', False),
                created_at=data.get('created_at')
            )
        return None

    @staticmethod
    def get_by_email(email):
        users = db.collection('users').where('email', '==', email).limit(1).stream()
        for doc in users:
            data = doc.to_dict()
            return User(
                id=doc.id,
                username=data.get('username'),
                email=data.get('email'),
                password=data.get('password'),
                auth_provider=data.get('auth_provider', 'local'),
                is_approved=data.get('is_approved', False),
                is_admin=data.get('is_admin', False),
                created_at=data.get('created_at')
            )
        return None

    def save(self):
        user_data = {
            'username': self.username,
            'email': self.email,
            'password': self.password,
            'auth_provider': self.auth_provider,
            'is_approved': self.is_approved,
            'is_admin': self.is_admin,
            'created_at': self.created_at
        }
        db.collection('users').document(self.id).set(user_data)

    def delete(self):
        db.collection('users').document(self.id).delete()

    def update_password(self, new_password):
        self.password = generate_password_hash(new_password)
        self.save()

    def update_username(self, new_username):
        self.username = new_username
        self.save()

    def check_password(self, password):
        if not self.password or self.auth_provider != 'local':
            return False
        return check_password_hash(self.password, password)

    @staticmethod
    def create_user(username, email, password=None, auth_provider='local', is_approved=None, is_admin=None):
        # Check if this is the first user
        users_count = len(list(db.collection('users').limit(1).stream()))
        is_first_user = (users_count == 0)
        
        # New doc reference to get a generated ID
        new_doc_ref = db.collection('users').document()
        
        hashed_pw = generate_password_hash(password) if password else None
        
        user = User(
            id=new_doc_ref.id,
            username=username,
            email=email,
            password=hashed_pw,
            auth_provider=auth_provider,
            is_approved=is_approved if is_approved is not None else is_first_user,
            is_admin=is_admin if is_admin is not None else is_first_user
        )
        user.save()
        return user
