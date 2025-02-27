from sqlalchemy import Column, Text, DateTime, String, Integer, event
from .base import Base
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)

class FixedResponse(Base):
    __tablename__ = 'Fixed Responses'
    id = Column(Integer, primary_key=True)
    incoming = Column(Text, nullable=False)
    trigger_keyword = Column(String(255), nullable=False)
    comment_response_text = Column(Text, nullable=True)
    direct_response_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


