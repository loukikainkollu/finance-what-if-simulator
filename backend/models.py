from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    scenarios: Mapped[List["Scenario"]] = relationship(
        "Scenario", back_populates="user", cascade="all, delete-orphan"
    )
    reports: Mapped[List["Report"]] = relationship(
        "Report", back_populates="user", cascade="all, delete-orphan"
    )
    usage: Mapped[Optional["Usage"]] = relationship(
        "Usage", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    employees: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_per_employee: Mapped[int] = mapped_column(Integer, nullable=False)
    marketing_spend: Mapped[int] = mapped_column(Integer, nullable=False)
    product_price: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="scenarios")
    reports: Mapped[List["Report"]] = relationship(
        "Report", back_populates="scenario", cascade="all, delete-orphan"
    )


class ReportType(str):
    PDF = "pdf"
    DOCX = "docx"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    report_type: Mapped[str] = mapped_column(
        SAEnum(ReportType.PDF, ReportType.DOCX, name="report_type_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="reports")
    scenario: Mapped[Optional["Scenario"]] = relationship("Scenario", back_populates="reports")


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    scenarios_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reports_exported: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_usage_user_id"),
    )

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="usage")