from ..models.database import db
from datetime import datetime, timezone

class AssistantRepository:
    def __init__(self, db_instance=None):
        self.db = db_instance or db

    def update_user_status(self, sender_id, status):
        """Update a user's status."""
        result = self.db.users.update_one(
            {"user_id": sender_id},
            {"$set": {
                "status": status,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        return result.modified_count > 0