from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from ..core.database import Base

class AccountCache(Base):
    __tablename__ = "account_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    qbo_account_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String, nullable=True) # e.g., Expense, Bank, Accounts Payable
    account_sub_type: Mapped[str] = mapped_column(String, nullable=True) # e.g., Checking, Credit Card, Travel
    classification: Mapped[str] = mapped_column(String, nullable=True) # e.g., Liability, Equity, Revenue, Expense
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AccountCache(id={self.id}, qbo_id={self.qbo_account_id}, name='{self.name}', type='{self.account_type}')>" 