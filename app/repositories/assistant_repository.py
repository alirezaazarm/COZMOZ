from ..models.user import User
from ..models.database import db
from datetime import datetime, timezone

class AssistantRepository:
    def __init__(self, db_instance=None, client_username=None):
        self.db = db_instance or db
        self.client_username = client_username

    def update_user_status(self, sender_id, status):
        """Update a user's status for the current client."""
        return User.update_status(sender_id, status, self.client_username)

    def get_user_by_id(self, user_id):
        """Get a user by ID for the current client."""
        return User.get_by_id(user_id, self.client_username)

    def get_user_messages(self, user_id, limit=50):
        """Get user messages for the current client."""
        return User.get_user_messages(user_id, limit, self.client_username)

    def add_assistant_message(self, user_id, response_text):
        """Add an assistant message for the current client."""
        from ..models.enums import MessageRole
        
        message_doc = User.create_message_document(
            text=response_text,
            role=MessageRole.ASSISTANT.value,
            timestamp=datetime.now(timezone.utc)
        )
        
        return User.add_direct_message(user_id, message_doc, self.client_username)

    def get_thread_id(self, user_id):
        """Get thread ID for a user in the current client."""
        user = User.get_by_id(user_id, self.client_username)
        return user.get('thread_id') if user else None

    def update_thread_id(self, user_id, thread_id):
        """Update thread ID for a user in the current client."""
        return User.update(user_id, {'thread_id': thread_id}, self.client_username)

    def get_waiting_users(self, cutoff_time=None):
        """Get waiting users for the current client."""
        return User.get_waiting_users(self.client_username, cutoff_time)

    def get_users_with_status(self, status, limit=50):
        """Get users with a specific status for the current client."""
        return User.get_users_with_status(status, self.client_username, limit)