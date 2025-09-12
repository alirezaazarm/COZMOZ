from ..models.user import User
from ..models.enums import Platform
from ..models.database import USERS_COLLECTION, db

class UserRepository:
    def __init__(self, db_instance=None, client_username=None):
        self.db = db_instance or db
        self.client_username = client_username
    
    def get_user_by_id(self, user_id):
        """Get a user by ID for the current client"""
        return User.get_by_id(user_id, self.client_username)
    
    def get_user_by_username(self, username):
        """Get a user by username for the current client"""
        return User.get_by_username(username, self.client_username)
    
    def create_user(self, user_id, username, status, thread_id=None, platform=None):
        """Create a new user for the current client"""
        if not self.client_username:
            raise ValueError("Client username is required for user creation")
        if platform is None:
            raise ValueError("platform is required for user creation")
        return User.create(user_id, username, self.client_username, status, thread_id, platform)
    
    def update_user(self, user_id, update_data):
        """Update a user for the current client"""
        return User.update(user_id, update_data, self.client_username)
    
    def update_user_status(self, user_id, status):
        """Update a user's status for the current client"""
        return User.update_status(user_id, status, self.client_username)
    
    def add_direct_message(self, user_id, message_doc):
        """Add a direct message to user for the current client"""
        return User.add_direct_message(user_id, message_doc, self.client_username)
    
    def get_users_with_status(self, status, limit=50):
        """Get users with a specific status for the current client"""
        return User.get_users_with_status(status, self.client_username, limit)
    
    def get_waiting_users(self, cutoff_time=None):
        """Get waiting users for the current client"""
        return User.get_waiting_users(self.client_username, cutoff_time)
    
    def get_user_messages(self, user_id, limit=50):
        """Get user messages for the current client"""
        return User.get_user_messages(user_id, limit, self.client_username)
    
    def get_user_messages_since(self, user_id, cutoff_time):
        """Get user messages since a specific time for the current client"""
        return User.get_user_messages_since(user_id, cutoff_time, self.client_username)