from sqlalchemy import Column, String, BigInteger, Text, DateTime, Enum, ForeignKey, text, Boolean, Index,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .base import Base
from .enums import MessageDirection, MessageStatus
from datetime import datetime, UTC

class DirectMessage(Base):
    __tablename__ = 'direct_messages'
    __table_args__ = (
        UniqueConstraint('message_id', name='unique_message_id'),
        Index('ix_pending_messages', 'sender_id', 'status', 'timestamp',
              postgresql_where=text("status = 'pending'"))
    )

    message_id = Column(String(255), primary_key=True)
    sender_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    recipient_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    message_text = Column(Text)
    media_type = Column(String(50))
    media_url = Column(Text)
    timestamp = Column(DateTime, nullable=False)
    status = Column(Enum(MessageStatus, values_callable=lambda x: [e.value for e in MessageStatus]), default=MessageStatus.PENDING.value)
    direction = Column(Enum(MessageDirection, values_callable=lambda x: [e.value for e in MessageDirection]), nullable=False)
    response_batch_id = Column(String(255))
    confirmed = Column(Boolean, default=False)

    sender = relationship("User", foreign_keys=[sender_id])
    recipient = relationship("User", foreign_keys=[recipient_id])

class AssistantResponse(Base):
    __tablename__ = 'assistant_responses'

    id = Column(BigInteger, primary_key=True)
    message_ids = Column(JSONB, nullable=False)
    response_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    assistant_status = Column(Enum(MessageStatus, values_callable=lambda x: [e.value for e in MessageStatus]), nullable=False)
    instagram_status = Column(Enum(MessageStatus, values_callable=lambda x: [e.value for e in MessageStatus]), nullable=False)
    sender_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)

    __table_args__ = (
        Index(
            'ix_response_message_ids',
            'message_ids',
            postgresql_using='gin',
            postgresql_ops={'message_ids': 'jsonb_path_ops'}
        ),
    )