from datetime import datetime, date
from decimal import Decimal
import uuid
from typing import Optional
from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    source_account_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    target_account_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 3), nullable=False)
    reference: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    interval_unit: Mapped[str] = mapped_column(String(16), default="month")  # 'day', 'week', 'month'
    interval_value: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")  # 'active', 'paused', 'cancelled'
    next_execution_at: Mapped[date] = mapped_column(Date, nullable=False)
    last_executed_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
