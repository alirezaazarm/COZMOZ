from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship , backref
from .base import Base

class Comment(Base):
    __tablename__ = 'comments'

    comment_id = Column(BigInteger, primary_key=True)
    post_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    comment_text = Column(Text, nullable=False)
    parent_comment_id = Column(BigInteger, ForeignKey('comments.comment_id'))
    timestamp = Column(DateTime, nullable=False)
    user = relationship("User")
    status = Column(String(50), default="not_replied")
    replies = relationship("Comment", backref=backref("parent", remote_side=[comment_id]), cascade="all, delete-orphan", single_parent=True )