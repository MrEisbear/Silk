from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permission_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)


class PermissionGroup(Base):
    __tablename__ = "permission_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class GroupPermission(Base):
    __tablename__ = "group_permissions"

    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("permission_groups.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class UserPermission(Base):
    __tablename__ = "user_permissions"

    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class UserGroup(Base):
    __tablename__ = "user_groups"

    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("permission_groups.id", ondelete="CASCADE"), primary_key=True)
