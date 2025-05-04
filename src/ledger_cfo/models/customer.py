from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
import datetime

from ..core.database import Base

class CustomerCache(Base):
    __tablename__ = "customer_cache"

    id = Column(Integer, primary_key=True, index=True)
    qbo_customer_id = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, index=True, nullable=False)
    email_address = Column(String, nullable=True)
    last_synced_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<CustomerCache(id={self.id}, qbo_id={self.qbo_customer_id}, name='{self.display_name}')>" 