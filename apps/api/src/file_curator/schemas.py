import re
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
    inspect_small_text: bool = False


class ScanRead(ORMModel):
    id: str
    source_id: str
    status: str
    mode: str
    hash_contents: bool
    inspect_small_text: bool
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


class JunkRule(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    enabled: bool = True
    order: int = Field(default=0, ge=0)
    action: Literal["keep", "review", "quarantine"] = "review"
    score: int = Field(default=0, ge=0, le=100)
    extensions: list[str] = []
    filename_contains: list[str] = []
    filename_regex: list[str] = []
    path_contains: list[str] = []
    max_size: int | None = Field(default=None, ge=0)
    min_size: int | None = Field(default=None, ge=0)
    empty_only: bool = False
    stop_on_match: bool = False


class JunkRulePack(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    version: str = "1.0.0"
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    protected_extensions: list[str] = [".srt", ".ass", ".ssa", ".nfo"]
    protected_names: list[str] = []
    protected_paths: list[str] = []
    rules: list[JunkRule] = []
    source: Literal["built_in", "personal", "snapshot"] = "built_in"
    read_only: bool = True
    current_version: int = 1


class JunkRulePackWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    protected_extensions: list[str] = [".srt", ".ass", ".ssa", ".nfo"]
    protected_names: list[str] = []
    protected_paths: list[str] = []
    rules: list[JunkRule] = []
    change_note: str = Field(default="", max_length=1000)


class JunkRulePackVersionRead(ORMModel):
    pack_id: str
    version: int
    change_note: str
    created_at: datetime


class JunkRulePackApply(BaseModel):
    workflow_id: str
    version: int | None = Field(default=None, ge=1)


class JunkRulePackValidation(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    rule_count: int = 0


class NameCleanupRule(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    enabled: bool = True
    order: int = Field(default=0, ge=0)
    kind: Literal[
        "remove_contains", "remove_prefix", "remove_suffix",
        "literal_replace", "regex_replace",
    ]
    pattern: str = Field(min_length=1, max_length=1000)
    replacement: str = Field(default="", max_length=1000)
    extensions: list[str] = []
    path_contains: list[str] = []
    stop_on_match: bool = False
    examples: list[dict[str, str]] = []


class NameCleanupPack(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    version: str = "1"
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    protected_names: list[str] = []
    protected_keywords: list[str] = []
    protected_regex: list[str] = []
    normalize_separators: bool = True
    normalize_width: bool = False
    deduplicate_words: bool = True
    max_name_length: int = Field(default=240, ge=1, le=255)
    rules: list[NameCleanupRule] = []
    source: Literal["built_in", "personal", "snapshot"] = "built_in"
    read_only: bool = True
    current_version: int = 1


class NameCleanupPackWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    protected_names: list[str] = []
    protected_keywords: list[str] = []
    protected_regex: list[str] = []
    normalize_separators: bool = True
    normalize_width: bool = False
    deduplicate_words: bool = True
    max_name_length: int = Field(default=240, ge=1, le=255)
    rules: list[NameCleanupRule] = []
    change_note: str = Field(default="", max_length=1000)


class NameCleanupPackVersionRead(ORMModel):
    pack_id: str
    version: int
    change_note: str
    created_at: datetime


class NameCleanupPackApply(BaseModel):
    workflow_id: str
    version: int | None = Field(default=None, ge=1)


class NameCleanupPackValidation(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    rule_count: int = 0


class NameCleanupSimulation(BaseModel):
    pack: NameCleanupPack
    relative_path: str


class Condition(BaseModel):
    field: str
    operator: Literal[
        "equals", "not_equals", "contains", "not_contains", "starts_with", "ends_with",
        "regex", "in", "greater_than", "less_than", "is_true", "is_false",
    ]
    value: Any = None


class ConditionGroup(BaseModel):
    mode: Literal["all", "any", "not"] = "all"
    conditions: list[Condition] = []
    groups: list["ConditionGroup"] = []


class WorkflowAction(BaseModel):
    kind: Literal[
        "run_processor", "extract_dates", "clean_name", "remove_number_patterns",
        "inherit_parent", "render_name", "keep", "move", "archive", "quarantine",
        "skip", "require_review",
    ]
    options: dict[str, Any] = {}


class RuleCard(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    order: int = Field(default=0, ge=0)
    conditions: ConditionGroup = ConditionGroup()
    actions: list[WorkflowAction] = []
    on_match: Literal["continue", "stop", "skip", "review"] = "continue"


class WorkflowStage(BaseModel):
    id: Literal[
        "scope", "filter", "extract", "clean", "classify", "target", "review", "execute"
    ]
    enabled: bool = True
    rules: list[RuleCard] = []


class WorkflowScopeConfig(BaseModel):
    include_subdirectories: bool = True
    max_depth: int | None = Field(default=None, ge=0, le=100)
    include_extensions: list[str] = []
    exclude_extensions: list[str] = []
    include_paths: list[str] = []
    exclude_paths: list[str] = []
    ignore_hidden: bool = True
    ignore_system_paths: bool = True
    min_size: int | None = Field(default=None, ge=0)
    max_size: int | None = Field(default=None, ge=0)
    modified_after_ns: int | None = Field(default=None, ge=0)
    modified_before_ns: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_ranges(self):
        if self.min_size is not None and self.max_size is not None and self.min_size > self.max_size:
            raise ValueError("workflow.scope_size_range_invalid")
        if self.modified_after_ns is not None and self.modified_before_ns is not None and self.modified_after_ns > self.modified_before_ns:
            raise ValueError("workflow.scope_time_range_invalid")
        return self


class AssociationPolicy(BaseModel):
    enabled: bool = True
    extensions: list[str] = [".srt", ".ass", ".ssa", ".nfo", ".jpg", ".jpeg", ".png"]
    uncertain_action: Literal["review", "keep"] = "review"


class ImpactThreshold(BaseModel):
    max_operations: int | None = Field(default=None, ge=1)
    max_quarantine: int | None = Field(default=None, ge=1)
    review_above_operations: int | None = Field(default=None, ge=1)


class WorkflowProtectionConfig(BaseModel):
    protected_paths: list[str] = []
    protected_extensions: list[str] = []
    protected_names: list[str] = []
    protected_keywords: list[str] = []
    protected_regex: list[str] = []

    @field_validator("protected_regex")
    @classmethod
    def valid_regex(cls, values: list[str]) -> list[str]:
        for value in values:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError("workflow.protection_regex_invalid") from exc
        return values


class TemplateExample(BaseModel):
    input_path: str
    expected_path: str | None = None
    expected_action: str | None = None


class WorkflowTemplateV2(BaseModel):
    schema_version: Literal[2] = 2
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    minimum_version: str = "1.0.0"
    preset: Literal["rename_only", "rename_and_organize"] = "rename_only"
    review_policy: Literal["conservative", "balanced", "automatic"] = "balanced"
    conflict_policy: Literal["review", "append_number", "skip", "stop"] = "review"
    required_processors: dict[str, str] = {}
    scope: WorkflowScopeConfig = WorkflowScopeConfig()
    association_policy: AssociationPolicy = AssociationPolicy()
    impact_threshold: ImpactThreshold = ImpactThreshold()
    protection: WorkflowProtectionConfig = WorkflowProtectionConfig()
    stages: list[WorkflowStage]
    examples: list[TemplateExample] = []


class WorkflowRulePackReference(BaseModel):
    pack_id: str
    version: int = Field(ge=1)


class RulePackSelection(BaseModel):
    pack_id: str
    version: int = Field(ge=1)


class RulePackResolution(BaseModel):
    rule_id: str
    status: Literal["resolved", "missing", "selection_required", "embedded"]
    requested: list[WorkflowRulePackReference] = []
    resolved: list[WorkflowRulePackReference] = []
    missing: list[WorkflowRulePackReference] = []
    embedded_count: int = 0
    message: str


class WorkflowTemplateResolution(BaseModel):
    valid: bool
    template: WorkflowTemplateV2 | None = None
    resolutions: list[RulePackResolution] = []
    available_rule_packs: list[JunkRulePack] = []
    available_cleanup_packs: list[NameCleanupPack] = []
    errors: list[str] = []
    warnings: list[str] = []
    ready_to_import: bool = False


class TemplateTextInput(BaseModel):
    content: str = Field(min_length=2, max_length=1_000_000)
    format: Literal["auto", "yaml", "json"] = "auto"


class TemplateValidationResult(BaseModel):
    valid: bool
    template: WorkflowTemplateV2 | None = None
    errors: list[str] = []
    warnings: list[str] = []
    missing_processors: list[str] = []
    risks: list[str] = []


class TemplateImportInput(TemplateTextInput):
    source_id: str | None = None
    rule_pack_selections: dict[str, list[RulePackSelection]] = {}


class RuleTestInput(BaseModel):
    rule: RuleCard
    relative_path: str
    size: int = Field(default=0, ge=0)
    mtime_ns: int = Field(default=0, ge=0)


class RuleTestResult(BaseModel):
    matched: bool
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    reasons: list[str]
    warnings: list[str]


class WorkflowSimulationInput(BaseModel):
    template: WorkflowTemplateV2
    relative_path: str
    size: int = Field(default=0, ge=0)
    mtime_ns: int = Field(default=0, ge=0)
    fields: dict[str, Any] = {}


class WorkflowSimulationStep(BaseModel):
    rule_id: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    reasons: list[str]
    warnings: list[str]


class WorkflowSimulationResult(BaseModel):
    original_path: str
    proposed_path: str
    action: str
    requires_review: bool
    fields: dict[str, Any]
    steps: list[WorkflowSimulationStep]


class WorkflowSummaryItem(BaseModel):
    key: Literal["scope", "recognize", "rename", "destination", "review"]
    status: Literal[
        "disabled", "enabled", "incomplete", "missing_dependency", "review", "ready"
    ]
    title: str
    value: str


class WorkflowLivePreviewInput(WorkflowSimulationInput):
    pass


class WorkflowLiveSummary(BaseModel):
    valid: bool
    can_preview: bool
    summary: list[WorkflowSummaryItem]
    diagnostics: list["WorkflowDiagnostic"]
    simulation: WorkflowSimulationResult


class DraftWorkflowImpactInput(BaseModel):
    template: WorkflowTemplateV2
    source_id: str
    draft_revision: str
    force: bool = False


class DraftWorkflowImpact(BaseModel):
    source_id: str
    draft_revision: str
    total: int
    rename: int
    move: int
    archive: int
    quarantine: int
    unchanged: int
    conflicts: int
    review: int
    related: int = 0
    automatic: bool = True
    stale: bool = False


class WorkflowDiagnostic(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str
    stage_id: str | None = None
    rule_id: str | None = None
    message: str
    suggestion: str


class WorkflowDiagnosticsResult(BaseModel):
    valid: bool
    errors: int
    warnings: int
    diagnostics: list[WorkflowDiagnostic]


class WorkflowDependency(BaseModel):
    feature: str
    requires: list[str]
    satisfied: bool
    message: str


class WorkflowImpactSummary(BaseModel):
    workflow_id: str
    source_id: str
    total: int
    rename: int
    move: int
    archive: int
    quarantine: int
    unchanged: int
    conflicts: int
    review: int


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


class WorkflowTemplateUpdate(BaseModel):
    template: WorkflowTemplateV2


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
    workflow_id: str | None = None
    generate_preview: bool = False
    interval_minutes: int = Field(default=1440, ge=1, le=525_600)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    interval_minutes: int | None = Field(default=None, ge=1, le=525_600)
    enabled: bool | None = None
    workflow_id: str | None = None
    generate_preview: bool | None = None


class ScheduleRead(ORMModel):
    id: str
    name: str
    source_id: str
    workflow_id: str | None
    generate_preview: bool
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
