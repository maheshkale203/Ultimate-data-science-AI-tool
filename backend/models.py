from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
import uuid 

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chats = relationship("ChatHistory", back_populates="owner", cascade="all, delete-orphan")
    
    # Remembers their current dataset
    active_file = Column(String, nullable=True) 

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    # Link back to the users table
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # This groups messages into a single chat thread!
    session_id = Column(String, index=True, default=lambda: str(uuid.uuid4()))

    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    
    # Automatically stamps the exact time the chat was saved
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Establish the relationship back to the user
    owner = relationship("User", back_populates="chats")