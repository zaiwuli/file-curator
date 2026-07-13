from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    root_path: str
    read_only: bool = False
    exclusions: list[str] = []
    protected_paths: list[str] = []


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    read_only: bool | None = None
    exclusions: list[str] | None = None
    protected_paths: list[str] | None = None


class SourceRead(ORMModel):
    id: str
    name: str
    root_path: str
    enabled: bool
    read_only: bool
    exclusions: list[str]
    protected_paths: list[str]
    capabilities: dict[str, Any]


class ScanCreate(BaseModel):
    source_id: str
    mode: Literal["full", "incremental"] = "full"


class ScanRead(ORMModel):
    id: str
    source_id: str
    status: str
    mode: str
    scanned_count: int
    error_count: int
    cursor: str | None
    errors: list[dict[str, Any]]
    completed_at: datetime | None


class FileRead(ORMModel):
    id: str
    source_id: str
    relative_path: str
    parent_path: str
    name: str
    extension: str
    size: int
    mtime_ns: int
    is_dir: bool


class ProcessorConfig(BaseModel):
    id: str
    enabled: bool = True
    options: dict[str, Any] = {}


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    preset: Literal["rename_only", "rename_and_organize"] = "rename_only"
    review_policy: Literal["conservative", "balanced", "automatic"] = "balanced"
    processors: list[ProcessorConfig] = []


class WorkflowRead(ORMModel):
    id: str
    name: str
    preset: str
    review_policy: str
    current_revision: int


class WorkflowRevisionCreate(BaseModel):
    processors: list[ProcessorConfig]
    review_policy: Literal["conservative", "balanced", "automatic"] | None = None


class PipelineRunCreate(BaseModel):
    source_id: str
    workflow_id: str


class PipelineRunRead(ORMModel):
    id: str
    source_id: str
    workflow_id: str
    workflow_revision: int
    status: str
    summary: dict[str, Any]


class StageResultRead(ORMModel):
    id: str
    file_entry_id: str
    processor_id: str
    processor_version: str
    status: str
    confidence: float
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    reasons: list[str]
    warnings: list[str]


class PlanCreate(BaseModel):
    run_id: str


class OperationRead(ORMModel):
    id: str
    sequence: int
    kind: str
    source_relative_path: str
    target_relative_path: str
    expected_size: int
    expected_mtime_ns: int
    reasons: list[str]
    reversible: bool


class PlanRead(ORMModel):
    id: str
    run_id: str
    source_id: str
    status: str
    frozen_at: datetime | None
    confirmed_at: datetime | None
    summary: dict[str, Any]
    operations: list[OperationRead]


class PlanOperationInput(BaseModel):
    kind: Literal["rename", "move", "quarantine"]
    source_relative_path: str
    target_relative_path: str
    group_id: str | None = None
    reasons: list[str] = []

    @field_validator("source_relative_path", "target_relative_path")
    @classmethod
    def relative_only(cls, value: str) -> str:
        if not value or value.startswith(("/", "\\")) or ":" in value:
            raise ValueError("path.must_be_relative")
        return value


class ManualPlanCreate(BaseModel):
    run_id: str
    operations: list[PlanOperationInput]


class BatchRead(ORMModel):
    id: str
    plan_id: str
    status: str
    succeeded: int
    failed: int
    skipped: int
    error: str | None
    completed_at: datetime | None


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_id: str
    interval_minutes: int = Field(default=1440, ge=1, le=525_600)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    interval_minutes: int | None = Field(default=None, ge=1, le=525_600)
    enabled: bool | None = None


class ScheduleRead(ORMModel):
    id: str
    name: str
    source_id: str
    interval_minutes: int
    enabled: bool
    next_run_at: datetime
    last_run_at: datetime | None


class DuplicateMember(BaseModel):
    id: str
    relative_path: str
    size: int
    content_hash: str | None


class DuplicateCandidate(BaseModel):
    key: str
    method: Literal["name_size", "normalized_name_size", "hash"]
    members: list[DuplicateMember]


class AuditRead(ORMModel):
    id: str
    batch_id: str | None
    operation_id: str | None
    event: str
    status: str
    details: dict[str, Any]
    created_at: datetime
