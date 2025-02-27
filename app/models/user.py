from sqlalchemy import Column, BigInteger, String, Text, DateTime, JSON
from sqlalchemy.exc import SQLAlchemyError
from .base import Base
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)

class User(Base):
    __tablename__ = 'users'

    assistant_thread_id = Column(String(255))
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=False, unique=True)
    full_name = Column(String(255))
    profile_picture_url = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    openai_metadata = Column(JSON)

    SYSTEM_SENDER_ID = 0
    SYSTEM_RECIPIENT_ID = 1

    @classmethod
    def get_or_create_system_users(cls, db):
        try:
            sender = db.get(cls, cls.SYSTEM_SENDER_ID)
            if not sender:
                sender = cls(
                    user_id=cls.SYSTEM_SENDER_ID,
                    username="system_sender",
                    full_name="System Sender Account"
                )
                db.add(sender)

            recipient = db.get(cls, cls.SYSTEM_RECIPIENT_ID)
            if not recipient:
                recipient = cls(
                    user_id=cls.SYSTEM_RECIPIENT_ID,
                    username="system_recipient",
                    full_name="System Recipient Account"
                )
                db.add(recipient)

            db.commit()
            return sender, recipient
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Failed to create system users: {str(e)}")
            raise