from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models.message import DirectMessage, MessageStatus
import logging

logger = logging.getLogger(__name__)

class MessageService:
    def __init__(self, db: Session):
        self.db = db

    def lock_and_get_messages(self, sender_id, cutoff_time):
        messages = self.db.execute(
            select(DirectMessage)
            .where(
                DirectMessage.sender_id == sender_id,
                DirectMessage.status == MessageStatus.PENDING,
                DirectMessage.timestamp >= cutoff_time
            )
            .with_for_update(skip_locked=True)
        ).scalars().all()
        for msg in messages:
            self.db.refresh(msg)
        return messages

    def update_message_statuses(self, messages, status):
        try:
            for msg in messages:
                msg.status = status
            self.db.flush()
        except Exception as e:
            logger.error(f"Failed to update message statuses: {str(e)}")
            self.db.rollback()
            raise

    def get_pending_users_query(self, cutoff_time):
        return (
            select(DirectMessage.sender_id)
            .where(
                DirectMessage.status == MessageStatus.PENDING,
                DirectMessage.timestamp >= cutoff_time
            )
            .group_by(DirectMessage.sender_id)
            .distinct()
        )