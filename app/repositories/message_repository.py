from ..models.enums import UserStatus, MessageRole
from ..models.database import db
from datetime import datetime, timezone

class MessageRepository:
    def __init__(self, db_instance=None):
        self.db = db_instance or db

    def get_waiting_users(self, cutoff_time):
        """Get users with WAITING status that have messages."""
        # Find users with WAITING status
        pipeline = [
            {"$match": {
                "status": UserStatus.WAITING.value,
                "direct_messages": {
                    "$elemMatch": {
                        "timestamp": {"$gte": cutoff_time}
                    }
                }
            }},
            {"$project": {"user_id": 1}}
        ]
        users = list(self.db.users.aggregate(pipeline))
        return [user['user_id'] for user in users]

    def get_user_messages(self, user_id, cutoff_time):
        """Get recent messages for a specific user."""
        # Find user and get their recent messages
        user = self.db.users.find_one(
            {"user_id": user_id, "status": UserStatus.WAITING.value},
            {"direct_messages": 1}
        )
        
        if not user or "direct_messages" not in user:
            return []
            
        # Filter messages by timestamp
        messages = []
        for msg in user.get("direct_messages", []):
            if cutoff_time is None or msg.get("timestamp", datetime.min) >= cutoff_time:
                messages.append(msg)
                
        # Sort by timestamp
        messages.sort(key=lambda x: x.get("timestamp", datetime.min))
        return messages

    def update_user_status(self, user_id, status):
        """Update a user's status."""
        result = self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    def save_response(self, response_text, user_id):
        """Save an assistant response and update user status."""
        # Create message document for assistant response
        message_doc = {
            "text": response_text,
            "role": MessageRole.ASSISTANT.value,
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Add message to user's direct_messages array and update status
        result = self.db.users.update_one(
            {"user_id": user_id},
            {
                "$push": {"direct_messages": message_doc},
                "$set": {"status": UserStatus.REPLIED.value, "updated_at": datetime.now(timezone.utc)}
            }
        )
        return result.modified_count > 0

    def update_status_for_completed_users(self, cutoff_time):
        """Update status for users who have received responses."""
        # Find users who have been in REPLIED status for a long time
        users = self.db.users.find({
            "status": UserStatus.REPLIED.value,
            "updated_at": {"$lt": cutoff_time}
        })
        
        # Update each user's status
        for user in users:
            user_id = user.get('user_id')
            self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"status": UserStatus.WAITING.value, "updated_at": datetime.now(timezone.utc)}}
            )