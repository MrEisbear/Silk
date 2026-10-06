from datetime import datetime
from decimal import Decimal
import uuid
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()))
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_account_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True)
    to_account_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 3), nullable=False)
    tax_category: Mapped[int] = mapped_column(SmallInteger, default=0)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Column in MariaDB is named `metadata` (mapped to attribute metadata_payload to avoid conflict with Base.metadata)
    metadata_payload: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def raw_metadata(self) -> Optional[str]:
        return self.metadata_payload
