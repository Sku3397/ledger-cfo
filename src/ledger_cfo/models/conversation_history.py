from sqlalchemy import Column, String, Integer, JSON, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..core.database import Base

class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False) # Order of turns within a conversation
    role = Column(String, nullable=False) # 'user', 'assistant', 'tool'
    content = Column(Text, nullable=True) # Raw content (text)
    content_json = Column(JSON, nullable=True) # Structured content (e.g., tool calls/results)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Add indexes for faster querying
    __table_args__ = (
        Index('ix_conversation_history_conv_id_seq', 'conversation_id', 'sequence'),
    )

    def to_dict(self):
        # Helper to convert model instance to a dictionary suitable for history lists
        # Prioritize json content if available
        turn_content = self.content_json if self.content_json is not None else self.content
        return {
            "role": self.role,
            "content": turn_content
            # Add other fields if needed by the LLM (e.g., name for tool role)
        } 