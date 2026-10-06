from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import DateTime, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class Token(Base):
    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    sender_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    recipient_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 3), nullable=False)
    tax: Mapped[int] = mapped_column(SmallInteger, default=1)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="issued")  # 'issued','used','expired','revoked'
    created: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
