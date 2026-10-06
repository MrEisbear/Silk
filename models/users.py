from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    last_salary_claim: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 'user', 'mod', 'admin'
    public_leaderboard: Mapped[bool] = mapped_column(Boolean, default=False)
