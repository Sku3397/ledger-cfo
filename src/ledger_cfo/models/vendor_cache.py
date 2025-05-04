from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from ..core.database import Base

class VendorCache(Base):
    __tablename__ = "vendor_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    qbo_vendor_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Add other relevant fields if needed, e.g., email, phone
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<VendorCache(id={self.id}, qbo_id={self.qbo_vendor_id}, name='{self.display_name}')>" 