from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Source(Base, TimestampMixin):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    root_path: Mapped[str] = mapped_column(Text, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusions: Mapped[list[str]] = mapped_column(JSON, default=list)
    protected_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ScanJob(Base, TimestampMixin):
    __tablename__ = "scan_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    mode: Mapped[str] = mapped_column(String(16), default="full")
    hash_contents: Mapped[bool] = mapped_column(Boolean, default=False)
    inspect_small_text: Mapped[bool] = mapped_column(Boolean, default=False)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[str | None] = mapped_column(Text)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[Source] = relationship()


class FileEntry(Base, TimestampMixin):
    __tablename__ = "file_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    relative_path: Mapped[str] = mapped_column(Text, index=True)
    parent_path: Mapped[str] = mapped_column(Text, default="")
    name: Mapped[str] = mapped_column(Text)
    extension: Mapped[str] = mapped_column(String(64), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    mtime_ns: Mapped[int] = mapped_column(Integer, default=0)
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_job_id: Mapped[str] = mapped_column(ForeignKey("scan_jobs.id", ondelete="CASCADE"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    text_signals: Mapped[list[str]] = mapped_column(JSON, default=list)


class FileGroup(Base, TimestampMixin):
    __tablename__ = "file_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    group_key: Mapped[str] = mapped_column(Text, index=True)
    group_type: Mapped[str] = mapped_column(String(64), default="related")
    member_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)


class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    preset: Mapped[str] = mapped_column(String(64), default="rename_only")
    review_policy: Mapped[str] = mapped_column(String(32), default="balanced")
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    revisions: Mapped[list["WorkflowRevision"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowRevision(Base, TimestampMixin):
    __tablename__ = "workflow_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    workflow: Mapped[Workflow] = relationship(back_populates="revisions")


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"))
    workflow_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="processing")
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class StageResult(Base, TimestampMixin):
    __tablename__ = "stage_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    file_entry_id: Mapped[str] = mapped_column(ForeignKey("file_entries.id", ondelete="CASCADE"))
    processor_id: Mapped[str] = mapped_column(String(100))
    processor_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, default=0)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)


class ReviewDecision(Base, TimestampMixin):
    __tablename__ = "review_decisions"
    __table_args__ = (UniqueConstraint("run_id", "file_entry_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    file_entry_id: Mapped[str] = mapped_column(
        ForeignKey("file_entries.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(32))
    target_relative_path: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    operations: Mapped[list["Operation"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="Operation.sequence"
    )


class Operation(Base, TimestampMixin):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    source_relative_path: Mapped[str] = mapped_column(Text)
    target_relative_path: Mapped[str] = mapped_column(Text)
    expected_size: Mapped[int] = mapped_column(Integer, default=0)
    expected_mtime_ns: Mapped[int] = mapped_column(Integer, default=0)
    group_id: Mapped[str | None] = mapped_column(String(36))
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    plan: Mapped[Plan] = relationship(back_populates="operations")


class ExecutionBatch(Base, TimestampMixin):
    __tablename__ = "execution_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("execution_batches.id"), index=True)
    operation_id: Mapped[str | None] = mapped_column(ForeignKey("operations.id"))
    event: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Database:
    def __init__(self, url: str):
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args, future=True)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def configure_sqlite(dbapi_connection: Any, _: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Path(self.engine.url.database or ".").parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        with self.session_factory() as session:
            yield session
