from datetime import datetime
from decimal import Decimal
import uuid
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    account_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    account_holder_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user', 'company', 'gov'
    account_holder_id: Mapped[str] = mapped_column(String(36), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 3), default=Decimal("0.000"), nullable=False)
    custom_account_name: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    pin_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pin_failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pin_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
