from sqlalchemy import Column, BigInteger, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base

class Product(Base):
    __tablename__ = 'products'

    pID = Column(BigInteger, primary_key=True)
    title = Column(Text, nullable=False)
    translated_title = Column(Text, nullable=True)
    category = Column(Text, nullable=False)
    tags = Column(Text)
    price = Column(JSON)
    excerpt = Column(Text)
    sku = Column(Text)
    description = Column(Text)
    stock_status = Column(Text, default="موجود")
    additional_info = Column(JSON)
    link = Column(Text, nullable=False)