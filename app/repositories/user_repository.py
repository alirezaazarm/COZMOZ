from ..models.user import User
from ..models.database import USERS_COLLECTION, db

class UserRepository:
    def __init__(self, db_instance=None):
        self.db = db_instance or db
    
    def get_or_create_system_users(self):
        # Check if system sender exists
        sender = self.db[USERS_COLLECTION].find_one({"user_id": User.SYSTEM_SENDER_ID})
        if not sender:
            # Create system sender
            sender_doc = User.create_user_document(
                user_id=User.SYSTEM_SENDER_ID,
                username="system_sender",
                full_name="System Sender Account"
            )
            self.db[USERS_COLLECTION].insert_one(sender_doc)
            sender = sender_doc
        
        # Check if system recipient exists
        recipient = self.db[USERS_COLLECTION].find_one({"user_id": User.SYSTEM_RECIPIENT_ID})
        if not recipient:
            # Create system recipient
            recipient_doc = User.create_user_document(
                user_id=User.SYSTEM_RECIPIENT_ID,
                username="system_recipient",
                full_name="System Recipient Account"
            )
            self.db[USERS_COLLECTION].insert_one(recipient_doc)
            recipient = recipient_doc
            
        return sender, recipient