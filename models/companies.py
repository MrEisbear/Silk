from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    company_type: Mapped[str] = mapped_column(String(16), default="private")  # 'private','public','government','association'
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    shares_total: Mapped[int] = mapped_column(BigInteger, default=100)
    trading_status: Mapped[str] = mapped_column(String(16), default="active")  # 'active','frozen','suspended','delisted'
    is_bankrupt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dissolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
