import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .config import Settings
from .db import (
    AuditLog,
    ExecutionBatch,
    FileEntry,
    FileGroup,
    Operation,
    PipelineRun,
    Plan,
    Source,
    StageResult,
    Workflow,
    WorkflowRevision,
    utcnow,
)
from .filesystem import FileSafetyError, normalize_root, resolve_inside
from .processors import ProcessingContext, ProcessorRegistry
from .schemas import ManualPlanCreate, ProcessorConfig


class DomainError(RuntimeError):
    def __init__(self, code: str, status_code: int = 400):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


DEFAULT_PROCESSORS = [
    ProcessorConfig(id="extract_date"),
    ProcessorConfig(id="extract_identifier"),
    ProcessorConfig(id="extract_sequence"),
    ProcessorConfig(id="extract_quality"),
    ProcessorConfig(id="extract_parent_context"),
    ProcessorConfig(id="normalize_name"),
]


def rebuild_file_groups(session: Session, source_id: str, entries: list[FileEntry]) -> int:
    """Create deterministic related-file groups without reading file contents."""
    session.query(FileGroup).filter_by(source_id=source_id).delete()
    candidates: dict[tuple[str, str], list[FileEntry]] = {}
    sequence_pattern = re.compile(
        r"(?i)(?:\s*[([]\d{1,3}[)\]]|\s*(?:part|pt|cd|ep)[ ._-]?\d{1,3})$"
    )
    for entry in entries:
        stem = sequence_pattern.sub("", Path(entry.name).stem).strip(" ._-").casefold()
        if stem:
            candidates.setdefault((entry.parent_path.casefold(), stem), []).append(entry)
    created = 0
    for (parent, stem), members in candidates.items():
        if len(members) < 2:
            continue
        session.add(
            FileGroup(
                source_id=source_id,
                group_key=f"{parent}/{stem}",
                group_type="related",
                member_ids=[
                    entry.id for entry in sorted(members, key=lambda item: item.relative_path)
                ],
                confidence=0.9,
                reasons=["group.normalized_stem_matched"],
            )
        )
        created += 1
    return created


def get_revision(session: Session, workflow: Workflow) -> WorkflowRevision:
    revision = (
        session.query(WorkflowRevision)
        .filter_by(workflow_id=workflow.id, revision=workflow.current_revision)
        .one_or_none()
    )
    if not revision:
        raise DomainError("workflow.revision_not_found", 404)
    return revision


def run_pipeline(
    session: Session, source: Source, workflow: Workflow, registry: ProcessorRegistry
) -> PipelineRun:
    revision = get_revision(session, workflow)
    processors = revision.config.get("processors", [])
    enabled = [item for item in processors if item.get("enabled", True)]
    registry.validate_order([item["id"] for item in enabled])
    run = PipelineRun(
        source_id=source.id,
        workflow_id=workflow.id,
        workflow_revision=revision.revision,
        status="processing",
    )
    session.add(run)
    session.flush()
    entries = (
        session.query(FileEntry).filter_by(source_id=source.id, active=True, is_dir=False).all()
    )
    changed = review = 0
    for entry in entries:
        context = ProcessingContext(
            entry_id=entry.id,
            relative_path=entry.relative_path,
            original_name=entry.name,
            parent_path=entry.parent_path,
            extension=entry.extension,
            size=entry.size,
            mtime_ns=entry.mtime_ns,
        )
        for item in enabled:
            processor = registry.get(item["id"])
            input_data = {
                "name": context.proposed_name or context.original_name,
                "parent": context.proposed_parent or context.parent_path,
                "fields": dict(context.fields),
            }
            result = processor.process(context, item.get("options", {}))
            context.fields.update(result.fields)
            if result.proposed_name is not None:
                context.proposed_name = result.proposed_name
            if result.proposed_parent is not None:
                context.proposed_parent = result.proposed_parent
            context.confidence = max(0.0, min(1.0, context.confidence + result.confidence_delta))
            context.reasons.extend(result.reasons)
            context.warnings.extend(result.warnings)
            session.add(
                StageResult(
                    run_id=run.id,
                    file_entry_id=entry.id,
                    processor_id=processor.manifest.id,
                    processor_version=processor.manifest.version,
                    status=result.status,
                    confidence=context.confidence,
                    input_data=input_data,
                    output_data={
                        "fields": dict(context.fields),
                        "proposed_name": context.proposed_name,
                        "proposed_parent": context.proposed_parent,
                    },
                    reasons=result.reasons,
                    warnings=result.warnings,
                )
            )
            if result.status in {"review", "warning"}:
                review += 1
        if context.proposed_name or context.proposed_parent:
            changed += 1
    groups = rebuild_file_groups(session, source.id, entries)
    run.status = "review" if review else "completed"
    run.summary = {"files": len(entries), "changed": changed, "review": review, "groups": groups}
    session.commit()
    return run


def create_plan_from_pipeline(session: Session, run: PipelineRun) -> Plan:
    if run.status not in {"completed", "review"}:
        raise DomainError("plan.pipeline_not_ready")
    latest: dict[str, StageResult] = {}
    for result in (
        session.query(StageResult).filter_by(run_id=run.id).order_by(StageResult.created_at).all()
    ):
        latest[result.file_entry_id] = result
    plan = Plan(run_id=run.id, source_id=run.source_id, status="draft")
    session.add(plan)
    session.flush()
    sequence = 0
    for file_id, result in latest.items():
        entry = session.get(FileEntry, file_id)
        if not entry:
            continue
        name = result.output_data.get("proposed_name") or entry.name
        parent = result.output_data.get("proposed_parent")
        if parent is None:
            parent = entry.parent_path
        target = (Path(parent) / name).as_posix() if parent else name
        if target == entry.relative_path:
            continue
        kind = "rename" if parent == entry.parent_path else "move"
        plan.operations.append(
            Operation(
                sequence=sequence,
                kind=kind,
                source_relative_path=entry.relative_path,
                target_relative_path=target,
                expected_size=entry.size,
                expected_mtime_ns=entry.mtime_ns,
                reasons=result.reasons,
            )
        )
        sequence += 1
    plan.summary = {"operation_count": len(plan.operations)}
    session.commit()
    return plan


def create_manual_plan(session: Session, payload: ManualPlanCreate) -> Plan:
    run = session.get(PipelineRun, payload.run_id)
    if not run:
        raise DomainError("pipeline_run.not_found", 404)
    plan = Plan(run_id=run.id, source_id=run.source_id, status="draft")
    session.add(plan)
    session.flush()
    for sequence, spec in enumerate(payload.operations):
        entry = (
            session.query(FileEntry)
            .filter_by(
                source_id=run.source_id, relative_path=spec.source_relative_path, active=True
            )
            .one_or_none()
        )
        if not entry:
            raise DomainError("operation.source_not_indexed")
        plan.operations.append(
            Operation(
                sequence=sequence,
                kind=spec.kind,
                source_relative_path=spec.source_relative_path,
                target_relative_path=spec.target_relative_path,
                expected_size=entry.size,
                expected_mtime_ns=entry.mtime_ns,
                group_id=spec.group_id,
                reasons=spec.reasons,
            )
        )
    plan.summary = {"operation_count": len(payload.operations)}
    session.commit()
    return plan


def freeze_plan(session: Session, plan: Plan) -> Plan:
    if plan.status != "draft":
        raise DomainError("plan.not_draft")
    source = session.get(Source, plan.source_id)
    if not source:
        raise DomainError("source.not_found", 404)
    root = normalize_root(source.root_path)
    targets: set[str] = set()
    for operation in plan.operations:
        source_path = resolve_inside(root, operation.source_relative_path, strict=True)
        target_path = resolve_inside(root, operation.target_relative_path)
        if source_path == root or target_path == root:
            raise DomainError("operation.root_forbidden")
        key = str(target_path).casefold()
        if key in targets:
            raise DomainError("operation.duplicate_target")
        targets.add(key)
        if target_path.exists() and target_path != source_path:
            raise DomainError("operation.target_exists")
        stat = source_path.stat()
        if not source_path.is_dir() and (
            stat.st_size != operation.expected_size
            or stat.st_mtime_ns != operation.expected_mtime_ns
        ):
            raise DomainError("operation.source_changed")
        if (
            Path(operation.source_relative_path).suffix.lower()
            != Path(operation.target_relative_path).suffix.lower()
        ):
            raise DomainError("operation.extension_changed")
    plan.status = "frozen"
    plan.frozen_at = utcnow()
    session.commit()
    return plan


def confirm_plan(session: Session, plan: Plan) -> Plan:
    if plan.status != "frozen":
        raise DomainError("plan.not_frozen")
    plan.status = "confirmed"
    plan.confirmed_at = utcnow()
    session.commit()
    return plan


def queue_plan_execution(session: Session, plan: Plan) -> ExecutionBatch:
    if plan.status != "confirmed":
        raise DomainError("plan.not_confirmed")
    batch = ExecutionBatch(plan_id=plan.id, status="queued")
    session.add(batch)
    plan.status = "queued"
    session.commit()
    return batch


def execute_batch(session: Session, batch: ExecutionBatch, settings: Settings) -> ExecutionBatch:
    plan = session.get(Plan, batch.plan_id)
    if not plan:
        raise DomainError("batch.plan_not_found", 404)
    source = session.get(Source, plan.source_id)
    if not source or source.read_only:
        raise DomainError("source.not_writable")
    root = normalize_root(source.root_path)
    batch.status = "running"
    plan.status = "executing"
    session.commit()
    successful_ids = {
        log.operation_id
        for log in session.query(AuditLog)
        .filter_by(batch_id=batch.id, event="operation.executed", status="success")
        .all()
    }
    for operation in plan.operations[: settings.execution_batch_size]:
        if operation.id in successful_ids:
            continue
        session.refresh(batch)
        if batch.status in {"pause_requested", "cancel_requested"}:
            batch.status = "paused" if batch.status == "pause_requested" else "cancelled"
            plan.status = batch.status
            session.commit()
            return batch
        source_path = resolve_inside(root, operation.source_relative_path, strict=True)
        target_relative = operation.target_relative_path
        if operation.kind == "quarantine":
            target_relative = (
                Path(settings.quarantine_name) / Path(target_relative).name
            ).as_posix()
        target_path = resolve_inside(root, target_relative)
        try:
            if target_path.exists() and target_path != source_path:
                raise FileSafetyError("operation.target_exists")
            stat = source_path.stat()
            if not source_path.is_dir() and (
                stat.st_size != operation.expected_size
                or stat.st_mtime_ns != operation.expected_mtime_ns
            ):
                raise FileSafetyError("operation.source_changed")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(target_path)
            batch.succeeded += 1
            session.add(
                AuditLog(
                    batch_id=batch.id,
                    operation_id=operation.id,
                    event="operation.executed",
                    status="success",
                    details={"from": operation.source_relative_path, "to": target_relative},
                )
            )
        except (OSError, FileSafetyError) as exc:
            batch.failed += 1
            batch.status = "failed"
            batch.error = getattr(exc, "code", type(exc).__name__)
            session.add(
                AuditLog(
                    batch_id=batch.id,
                    operation_id=operation.id,
                    event="operation.executed",
                    status="failed",
                    details={"error": batch.error},
                )
            )
            session.commit()
            break
        session.commit()
    if batch.failed == 0 and batch.status == "running":
        batch.status = "completed"
        plan.status = "completed"
    else:
        plan.status = "failed"
    batch.completed_at = utcnow()
    session.commit()
    return batch


def rollback_batch(session: Session, batch: ExecutionBatch) -> ExecutionBatch:
    if batch.status not in {"completed", "failed", "paused", "cancelled"}:
        raise DomainError("batch.not_rollbackable")
    plan = session.get(Plan, batch.plan_id)
    source = session.get(Source, plan.source_id) if plan else None
    if not plan or not source:
        raise DomainError("batch.plan_not_found", 404)
    root = normalize_root(source.root_path)
    successful_ids = {
        log.operation_id
        for log in session.query(AuditLog)
        .filter_by(batch_id=batch.id, event="operation.executed", status="success")
        .all()
    }
    for operation in reversed(plan.operations):
        if operation.id not in successful_ids:
            continue
        current_relative = operation.target_relative_path
        if operation.kind == "quarantine":
            current_relative = (
                Path(".file-curator-quarantine") / Path(operation.target_relative_path).name
            ).as_posix()
        current = resolve_inside(root, current_relative, strict=True)
        original = resolve_inside(root, operation.source_relative_path)
        if original.exists():
            raise DomainError("rollback.target_exists")
        original.parent.mkdir(parents=True, exist_ok=True)
        current.rename(original)
        session.add(
            AuditLog(
                batch_id=batch.id,
                operation_id=operation.id,
                event="operation.rolled_back",
                status="success",
                details={"from": current_relative, "to": operation.source_relative_path},
            )
        )
    batch.status = "rolled_back"
    plan.status = "rolled_back"
    session.commit()
    return batch


def create_backup(session: Session, settings: Settings) -> Path:
    database_name = make_url(settings.resolved_database_url).database
    database = Path(database_name) if database_name else Path()
    if not database.exists():
        raise DomainError("backup.database_not_found")
    destination = (
        settings.config_dir / "backups" / f"file-curator-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    session.commit()
    shutil.copy2(database, destination)
    return destination
