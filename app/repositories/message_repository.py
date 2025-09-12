from ..models.enums import UserStatus, MessageRole, Platform
from ..models.user import User
from ..models.database import db
from datetime import datetime, timezone

class MessageRepository:
    def __init__(self, db_instance=None, client_username=None):
        self.db = db_instance or db
        self.client_username = client_username

    def get_waiting_users(self, cutoff_time):
        """Get users with WAITING status that have messages for the current client."""
        return User.get_waiting_users(self.client_username, cutoff_time)

    def get_user_messages(self, user_id, cutoff_time):
        """Get recent messages for a specific user in the current client."""
        if cutoff_time:
            return User.get_user_messages_since(user_id, cutoff_time, self.client_username)
        else:
            return User.get_user_messages(user_id, 50, self.client_username)

    def update_user_status(self, user_id, status):
        """Update a user's status for the current client."""
        return User.update_status(user_id, status, self.client_username)

    def save_response(self, response_text, user_id):
        """Save an assistant response and update user status for the current client."""
        # Create message document for assistant response
        message_doc = User.create_message_document(
            text=response_text,
            role=MessageRole.ASSISTANT.value,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add message to user's direct_messages array
        success = User.add_direct_message(user_id, message_doc, self.client_username)
        
        if success:
            # Update user status
            User.update_status(user_id, UserStatus.ASSISTANT_REPLIED.value, self.client_username)
        
        return success

    def update_status_for_completed_users(self, cutoff_time):
        """Update status for users who have received responses in the current client."""
        # This would need to be implemented using the User model methods
        # For now, we'll use direct database access with client filtering
        query = {
            "status": UserStatus.ASSISTANT_REPLIED.value,
            "updated_at": {"$lt": cutoff_time}
        }
        
        if self.client_username:
            query["client_username"] = self.client_username
        
        # Find users who have been in REPLIED status for a long time
        users = self.db.users.find(query)
        
        # Update each user's status
        for user in users:
            user_id = user.get('user_id')
            User.update_status(user_id, UserStatus.WAITING.value, self.client_username)

    def add_user_message(self, user_id, message_text, media_type=None, media_url=None, mid=None):
        """Add a user message for the current client."""
        message_doc = User.create_message_document(
            text=message_text,
            role=MessageRole.USER.value,
            media_type=media_type,
            media_url=media_url,
            timestamp=datetime.now(timezone.utc),
            mid=mid
        )
        
        return User.add_direct_message(user_id, message_doc, self.client_username)

    def check_message_exists(self, user_id, mid):
        """Check if a message with the given MID exists for the current client."""
        return User.check_mid_exists(user_id, mid, self.client_username)

    def get_user_by_id(self, user_id):
        """Get a user by ID for the current client."""
        return User.get_by_id(user_id, self.client_username)

    def create_user_if_not_exists(self, user_id, username, status=UserStatus.WAITING.value, platform=None):
        """Create a user if they don't exist for the current client."""
        if not self.client_username:
            raise ValueError("Client username is required for user creation")
            
        existing_user = User.get_by_id(user_id, self.client_username)
        if not existing_user:
            if platform is None:
                raise ValueError("platform is required for user creation")
            return User.create(user_id, username, self.client_username, status, platform=platform)
        return existing_user