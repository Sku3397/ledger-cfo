from sqlalchemy import Column, String, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timedelta
import uuid

from ..core.database import Base

class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_details: Mapped[dict] = mapped_column(JSON, nullable=False)
    original_email_id: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='PENDING', nullable=False) # PENDING, CONFIRMED, CANCELLED, EXPIRED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return f"<PendingAction(id={self.id}, status='{self.status}', expires_at='{self.expires_at}')>" 