from sqlalchemy.orm import Session
from ..models.user import User

class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_system_users(self):
        sender = self.session.query(User).get(User.SYSTEM_SENDER_ID)
        if not sender:
            sender = User(
                user_id=User.SYSTEM_SENDER_ID,
                username="system_sender",
                full_name="System Sender Account"
            )
            self.session.add(sender)

        recipient = self.session.query(User).get(User.SYSTEM_RECIPIENT_ID)
        if not recipient:
            recipient = User(
                user_id=User.SYSTEM_RECIPIENT_ID,
                username="system_recipient",
                full_name="System Recipient Account"
            )
            self.session.add(recipient)
        self.session.commit()
        return sender, recipient