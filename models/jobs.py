from decimal import Decimal
from typing import Optional
from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base

class SalaryClass(Base):
    __tablename__ = "salary_classes"

    class_level: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    daily_amount: Mapped[Decimal] = mapped_column(Numeric(19, 3), nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    salary_class: Mapped[Optional[int]] = mapped_column(SmallInteger, ForeignKey("salary_classes.class_level"), nullable=True)
    parent_job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=True)


class UserJob(Base):
    __tablename__ = "user_jobs"

    user_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("users.uuid", ondelete="CASCADE"), primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), primary_key=True)


class JobPermission(Base):
    __tablename__ = "job_permissions"

    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id"), primary_key=True)
