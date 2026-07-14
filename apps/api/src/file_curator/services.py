import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    ReviewDecision,
    Source,
    StageResult,
    Workflow,
    WorkflowRevision,
    utcnow,
)
from .filesystem import FileSafetyError, normalize_root, resolve_inside
from .processors import ProcessingContext, ProcessorRegistry
from .schemas import ManualPlanCreate, ProcessorConfig
from .workflow_engine import run_template_entry
from .workflow_templates import template_from_revision


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
    ProcessorConfig(id="extract_language"),
    ProcessorConfig(id="classify_extension"),
    ProcessorConfig(id="normalize_name"),
]


def _entry_in_scope(entry: FileEntry, scope: Any) -> bool:
    path = Path(entry.relative_path)
    parts = path.parts
    extension = entry.extension.casefold()
    if not scope.include_subdirectories and len(parts) > 1:
        return False
    if scope.max_depth is not None and len(parts) - 1 > scope.max_depth:
        return False
    if scope.include_extensions and extension not in {value.casefold() for value in scope.include_extensions}:
        return False
    if extension in {value.casefold() for value in scope.exclude_extensions}:
        return False
    relative = entry.relative_path.casefold()
    if scope.include_paths and not any(value.casefold() in relative for value in scope.include_paths):
        return False
    if any(value.casefold() in relative for value in scope.exclude_paths):
        return False
    if scope.ignore_hidden and any(part.startswith(".") for part in parts):
        return False
    if scope.ignore_system_paths and any(part.casefold() in {"$recycle.bin", "system volume information"} for part in parts):
        return False
    if scope.min_size is not None and entry.size < scope.min_size:
        return False
    if scope.max_size is not None and entry.size > scope.max_size:
        return False
    if scope.modified_after_ns is not None and entry.mtime_ns < scope.modified_after_ns:
        return False
    if scope.modified_before_ns is not None and entry.mtime_ns > scope.modified_before_ns:
        return False
    return True


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
    template = (
        template_from_revision(workflow.name, workflow.preset, workflow.review_policy, revision.config)
        if "template" in revision.config
        else None
    )
    if template is None:
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
    if template:
        entries = [entry for entry in entries if _entry_in_scope(entry, template.scope)]
    hash_groups: dict[str, list[FileEntry]] = {}
    for entry in entries:
        if entry.content_hash:
            hash_groups.setdefault(entry.content_hash, []).append(entry)
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
            fields={
                "text_signals": entry.text_signals,
                "hash_duplicate_count": len(hash_groups.get(entry.content_hash or "", [])),
                "hash_directory_count": len({
                    item.parent_path
                    for item in hash_groups.get(entry.content_hash or "", [])
                }),
            },
        )
        if template:
            traces = run_template_entry(template, context, registry)
            for trace in traces:
                session.add(StageResult(
                    run_id=run.id,
                    file_entry_id=entry.id,
                    processor_id=trace.rule_id,
                    processor_version="2.0.0",
                    status=trace.status,
                    confidence=context.confidence,
                    input_data=trace.input_data,
                    output_data=trace.output_data,
                    reasons=trace.reasons,
                    warnings=trace.warnings,
                ))
                if trace.status in {"review", "warning"}:
                    review += 1
        else:
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
        if (context.proposed_name or context.proposed_parent) and not context.fields.get("skip"):
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
    review_required: set[str] = set()
    results = (
        session.query(StageResult).filter_by(run_id=run.id).order_by(StageResult.created_at).all()
    )
    for result in results:
        # A condition-miss trace is informational and must not erase the last
        # matched action's proposed name, target, or operation kind.
        if result.status != "skipped" or result.file_entry_id not in latest:
            latest[result.file_entry_id] = result
        if result.status in {"review", "warning"}:
            review_required.add(result.file_entry_id)
    decisions = {
        decision.file_entry_id: decision
        for decision in session.query(ReviewDecision).filter_by(run_id=run.id).all()
    }
    plan = Plan(run_id=run.id, source_id=run.source_id, status="draft")
    session.add(plan)
    session.flush()
    sequence = 0
    unresolved = kept = overridden = conflicts = 0
    workflow = session.get(Workflow, run.workflow_id)
    conflict_policy = "review"
    if workflow:
        revision = get_revision(session, workflow)
        if "template" in revision.config:
            conflict_policy = revision.config["template"].get("conflict_policy", "review")
    source = session.get(Source, run.source_id)
    root = normalize_root(source.root_path) if source else None
    reserved_targets: set[str] = set()
    for file_id, result in latest.items():
        entry = session.get(FileEntry, file_id)
        if not entry:
            continue
        decision = decisions.get(file_id)
        if file_id in review_required and decision is None:
            unresolved += 1
            continue
        if decision and decision.action == "keep":
            kept += 1
            continue
        if decision and decision.action == "override":
            target = decision.target_relative_path
            if not target:
                raise DomainError("review.override_target_required")
            overridden += 1
        else:
            name = result.output_data.get("proposed_name") or entry.name
            parent = result.output_data.get("proposed_parent")
            if parent is None:
                parent = entry.parent_path
            target = (Path(parent) / name).as_posix() if parent else name
        requested_kind = result.output_data.get("fields", {}).get("operation_kind")
        if target == entry.relative_path and requested_kind != "quarantine":
            continue
        candidate = (
            (Path(".file-curator-quarantine") / Path(target).name).as_posix()
            if requested_kind == "quarantine"
            else target
        )
        target_exists = root is not None and resolve_inside(root, candidate).exists()
        target_key = candidate.casefold()
        has_conflict = target_key in reserved_targets or target_exists
        if has_conflict and conflict_policy == "append_number":
            path = Path(candidate)
            counter = 1
            while target_key in reserved_targets or (
                root is not None and resolve_inside(root, candidate).exists()
            ):
                candidate = (path.parent / f"{path.stem} ({counter}){path.suffix}").as_posix()
                target_key = candidate.casefold()
                counter += 1
            target = candidate
        elif has_conflict:
            conflicts += 1
            if conflict_policy == "stop":
                raise DomainError("operation.target_conflict")
            if conflict_policy == "review":
                unresolved += 1
                existing_conflict = session.query(StageResult).filter_by(
                    run_id=run.id,
                    file_entry_id=entry.id,
                    processor_id="plan.target_conflict",
                ).one_or_none()
                if existing_conflict is None:
                    session.add(StageResult(
                        run_id=run.id,
                        file_entry_id=entry.id,
                        processor_id="plan.target_conflict",
                        processor_version="2.0.0",
                        status="review",
                        confidence=result.confidence,
                        input_data={"source": entry.relative_path},
                        output_data=result.output_data,
                        reasons=["plan.target_conflict"],
                        warnings=[f"operation.target_exists:{candidate}"],
                    ))
            continue
        reserved_targets.add(candidate.casefold())
        target_parent = Path(target).parent.as_posix()
        if target_parent == ".":
            target_parent = ""
        kind = "quarantine" if requested_kind == "quarantine" else "rename" if target_parent == entry.parent_path else "move"
        reasons = list(result.reasons)
        if decision:
            reasons.append(f"review.{decision.action}")
        plan.operations.append(
            Operation(
                sequence=sequence,
                kind=kind,
                source_relative_path=entry.relative_path,
                target_relative_path=target,
                expected_size=entry.size,
                expected_mtime_ns=entry.mtime_ns,
                reasons=reasons,
            )
        )
        sequence += 1
    if workflow and "template" in get_revision(session, workflow).config:
        policy = get_revision(session, workflow).config["template"].get("association_policy", {})
        if policy.get("enabled", True):
            allowed = {str(value).casefold() for value in policy.get("extensions", [])}
            existing_sources = {operation.source_relative_path for operation in plan.operations}
            associated: list[Operation] = []
            for operation in list(plan.operations):
                if operation.kind not in {"rename", "move"} or Path(operation.source_relative_path).suffix.casefold() in allowed:
                    continue
                main_entry = session.query(FileEntry).filter_by(
                    source_id=run.source_id, relative_path=operation.source_relative_path
                ).one_or_none()
                if not main_entry:
                    continue
                main_stem = Path(main_entry.name).stem.casefold()
                target_path = Path(operation.target_relative_path)
                for sidecar in entries_for_source(session, run.source_id, main_entry.parent_path):
                    if sidecar.relative_path in existing_sources or sidecar.id == main_entry.id:
                        continue
                    if sidecar.extension.casefold() not in allowed or not Path(sidecar.name).stem.casefold().startswith(main_stem):
                        continue
                    suffix = Path(sidecar.name).stem[len(main_stem):]
                    side_target = (target_path.parent / f"{target_path.stem}{suffix}{Path(sidecar.name).suffix}").as_posix()
                    associated.append(Operation(
                        sequence=sequence + len(associated),
                        kind=operation.kind,
                        source_relative_path=sidecar.relative_path,
                        target_relative_path=side_target,
                        expected_size=sidecar.size,
                        expected_mtime_ns=sidecar.mtime_ns,
                        reasons=["association.same_stem", *operation.reasons],
                    ))
                    existing_sources.add(sidecar.relative_path)
            plan.operations.extend(associated)
            sequence += len(associated)
    plan.summary = {
        "operation_count": len(plan.operations),
        "unresolved_review_count": unresolved,
        "kept_count": kept,
        "overridden_count": overridden,
        "conflict_count": conflicts,
    }
    session.commit()
    return plan


def entries_for_source(session: Session, source_id: str, parent_path: str) -> list[FileEntry]:
    return session.query(FileEntry).filter_by(
        source_id=source_id, parent_path=parent_path, active=True, is_dir=False
    ).all()


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


def preflight_plan(session: Session, plan: Plan) -> dict[str, int | str]:
    if plan.status not in {"draft", "frozen", "confirmed", "queued"}:
        raise DomainError("plan.not_preflightable")
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
    return {"status": "ready", "operation_count": len(plan.operations)}


def freeze_plan(session: Session, plan: Plan) -> Plan:
    if plan.status != "draft":
        raise DomainError("plan.not_draft")
    preflight_plan(session, plan)
    run = session.get(PipelineRun, plan.run_id)
    workflow = session.get(Workflow, run.workflow_id) if run else None
    if workflow:
        revision = get_revision(session, workflow)
        template_data = revision.config.get("template", {})
        threshold = template_data.get("impact_threshold", {})
        operation_count = len(plan.operations)
        quarantine_count = sum(operation.kind == "quarantine" for operation in plan.operations)
        if threshold.get("max_operations") is not None and operation_count > threshold["max_operations"]:
            raise DomainError("plan.impact_threshold_operations")
        if threshold.get("max_quarantine") is not None and quarantine_count > threshold["max_quarantine"]:
            raise DomainError("plan.impact_threshold_quarantine")
        if threshold.get("review_above_operations") is not None and operation_count > threshold["review_above_operations"] and int(plan.summary.get("unresolved_review_count", 0)) > 0:
            raise DomainError("plan.impact_threshold_review")
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
    pending = [operation for operation in plan.operations if operation.id not in successful_ids]
    for operation in pending[: settings.execution_batch_size]:
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
            if not target_path.exists():
                raise FileSafetyError("operation.verification_failed")
            if not target_path.is_dir() and target_path.stat().st_size != operation.expected_size:
                raise FileSafetyError("operation.verification_failed")
            batch.succeeded += 1
            successful_ids.add(operation.id)
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
    if batch.failed:
        plan.status = "failed"
        batch.completed_at = utcnow()
    elif batch.status == "running" and len(successful_ids) < len(plan.operations):
        batch.status = "queued"
        plan.status = "executing"
        batch.completed_at = None
    elif batch.status == "running":
        batch.status = "completed"
        plan.status = "completed"
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
    with sqlite3.connect(database) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)
    return destination


def restore_backup(settings: Settings, filename: str) -> Path:
    if Path(filename).name != filename:
        raise DomainError("backup.invalid_filename")
    source = settings.config_dir / "backups" / filename
    if not source.is_file():
        raise DomainError("backup.not_found", 404)
    database_name = make_url(settings.resolved_database_url).database
    if not database_name:
        raise DomainError("backup.database_not_file")
    destination = Path(database_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection:
        integrity = source_connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise DomainError("backup.integrity_failed")
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)
    return destination
