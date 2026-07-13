from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    hash_contents: bool = False


class ScanRead(ORMModel):
    id: str
    source_id: str
    status: str
    mode: str
    hash_contents: bool
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


class FilePage(BaseModel):
    items: list[FileRead]
    total: int
    limit: int
    offset: int


class FileGroupRead(ORMModel):
    id: str
    source_id: str
    group_key: str
    group_type: str
    member_ids: list[str]
    confidence: float
    reasons: list[str]


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


class WorkflowRevisionRead(ORMModel):
    id: str
    workflow_id: str
    revision: int
    config: dict[str, Any]
    created_at: datetime


class WorkflowPortable(BaseModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    preset: Literal["rename_only", "rename_and_organize"] = "rename_only"
    review_policy: Literal["conservative", "balanced", "automatic"] = "balanced"
    processors: list[ProcessorConfig]


class WorkflowCompare(BaseModel):
    workflow_id: str
    from_revision: int
    to_revision: int
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]


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


class ReviewDecisionUpsert(BaseModel):
    action: Literal["accept", "keep", "override"]
    target_relative_path: str | None = None
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("target_relative_path")
    @classmethod
    def relative_target_only(cls, value: str | None) -> str | None:
        if value is not None and (
            not value or value.startswith(("/", "\\")) or ":" in value
        ):
            raise ValueError("path.must_be_relative")
        return value

    @model_validator(mode="after")
    def validate_target(self):
        if self.action == "override" and not self.target_relative_path:
            raise ValueError("review.override_target_required")
        if self.action != "override" and self.target_relative_path is not None:
            raise ValueError("review.target_only_for_override")
        return self


class ReviewDecisionRead(ORMModel):
    id: str
    run_id: str
    file_entry_id: str
    action: str
    target_relative_path: str | None
    note: str | None
    updated_at: datetime


class ReviewItemRead(BaseModel):
    run_id: str
    file_entry_id: str
    relative_path: str
    proposed_relative_path: str
    confidence: float
    reasons: list[str]
    warnings: list[str]
    processors: list[str]
    decision: ReviewDecisionRead | None = None


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


class PreflightRead(BaseModel):
    status: Literal["ready"]
    operation_count: int


class RollbackPreviewItem(BaseModel):
    operation_id: str
    source_relative_path: str
    target_relative_path: str
    ready: bool
    conflict: str | None = None


class RollbackPreview(BaseModel):
    batch_id: str
    ready: bool
    operations: list[RollbackPreviewItem]


class BackupRead(BaseModel):
    filename: str
    size: int
    created_at: datetime


class DiagnosticsRead(BaseModel):
    version: str
    worker_alive: bool
    database: str
    config_writable: bool
    webhook_configured: bool
    counts: dict[str, int]


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
