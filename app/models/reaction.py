from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class Reaction(Base):
    __tablename__ = 'reactions'

    reaction_id = Column(String(255), primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    content_type = Column(String(50), nullable=False)
    content_id = Column(String(255), nullable=False)
    reaction_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime, nullable=False)

    user = relationship("User")