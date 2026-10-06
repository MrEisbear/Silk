from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class GiftCode(Base):
    __tablename__ = "gift_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BCD")
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    redeemed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
