from sqlalchemy.orm import Session
from ..models.message import DirectMessage, AssistantResponse, MessageStatus

class MessageRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_pending_users(self, cutoff_time):
        return self.session.query(DirectMessage.sender_id).filter(
            DirectMessage.status == MessageStatus.PENDING.value,
            DirectMessage.timestamp >= cutoff_time
        ).distinct().all()

    def lock_and_get_messages(self, sender_id, cutoff_time):
        return self.session.query(DirectMessage).filter(
            DirectMessage.sender_id == sender_id,
            DirectMessage.status == MessageStatus.PENDING.value,
            DirectMessage.timestamp >= cutoff_time
        ).with_for_update(skip_locked=True).all()

    def update_status(self, messages, status):
        for msg in messages:
            msg.status = status
        self.session.commit()

    def save_response(self, message_ids, response_text, sender_id):
        response = AssistantResponse(
            message_ids=message_ids,
            response_text=response_text,
            assistant_status=MessageStatus.ASSISTANT_RESPONDED.value,
            instagram_status=MessageStatus.PENDING.value,
            sender_id=sender_id
        )
        self.session.add(response)
        self.session.commit()

    def cleanup_confirmed_messages(self, cutoff_time):
        self.session.query(DirectMessage).filter(
            DirectMessage.status == MessageStatus.REPLIED_TO_INSTAGRAM.value,
            DirectMessage.timestamp < cutoff_time,
            DirectMessage.confirmed == True
        ).update({"status": MessageStatus.COMPLETED.value}, synchronize_session=False)
        self.session.commit()