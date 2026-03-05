"""SQLAlchemy ORM models for the EvoSys storage layer."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class TrajectoryRow(Base):
    """Persisted representation of a :class:`TrajectoryRecord`."""

    __tablename__ = "trajectory_records"

    trace_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(26), index=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    iteration_index: Mapped[int] = mapped_column(Integer)
    context_summary: Mapped[str] = mapped_column(Text)
    llm_reasoning: Mapped[str] = mapped_column(Text, default="")
    action_name: Mapped[str] = mapped_column(String(256), index=True)
    action_params_json: Mapped[str] = mapped_column(Text, default="{}")
    action_result_json: Mapped[str] = mapped_column(Text, default="{}")
    token_cost: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    skill_used: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_trajectory_session_ts", "session_id", "timestamp_utc"),
    )


class MemoryRow(Base):
    """Persistent key-value memory for the agent across sessions."""

    __tablename__ = "agent_memory"

    namespace: Mapped[str] = mapped_column(String(256), primary_key=True, default="default")
    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        Index("ix_memory_namespace", "namespace"),
    )


class ScheduledTaskRow(Base):
    """A user-defined task the agent runs on a recurring schedule.

    The agent executes *description* as a plain-language task and stores
    the answer in *last_result_json*.  Results are also written to the
    agent_memory table under ``alert:{task_id}:latest`` so the user can
    retrieve them with the recall tool.
    """

    __tablename__ = "scheduled_tasks"

    task_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    interval_seconds: Mapped[int] = mapped_column(Integer)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_result_json: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

