import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .db import (
    AuditLog,
    Database,
    ExecutionBatch,
    FileEntry,
    FileGroup,
    PipelineRun,
    Plan,
    ReviewDecision,
    ScanJob,
    Schedule,
    Source,
    StageResult,
    Workflow,
    WorkflowRevision,
)
from .filesystem import FileSafetyError, normalize_root, probe_capabilities, resolve_inside
from .junk_rules import DEFAULT_JUNK_PACK, junk_pack_dict
from .processors import ProcessingContext, create_default_registry
from .schemas import (
    AuditRead,
    BackupRead,
    BatchRead,
    DiagnosticsRead,
    DuplicateCandidate,
    FileGroupRead,
    FilePage,
    FileRead,
    JunkRulePack,
    JunkRulePackValidation,
    ManualPlanCreate,
    PipelineRunCreate,
    PipelineRunRead,
    PlanCreate,
    PlanRead,
    PreflightRead,
    ReviewDecisionRead,
    ReviewDecisionUpsert,
    ReviewItemRead,
    RollbackPreview,
    RuleTestInput,
    RuleTestResult,
    ScanCreate,
    ScanRead,
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
    SourceCreate,
    SourceRead,
    SourceUpdate,
    StageResultRead,
    TemplateImportInput,
    TemplateTextInput,
    TemplateValidationResult,
    WorkflowCompare,
    WorkflowCreate,
    WorkflowImpactSummary,
    WorkflowPortable,
    WorkflowRead,
    WorkflowRevisionCreate,
    WorkflowRevisionRead,
    WorkflowStage,
    WorkflowTemplateUpdate,
    WorkflowTemplateV2,
)
from .services import (
    DEFAULT_PROCESSORS,
    DomainError,
    confirm_plan,
    create_backup,
    create_manual_plan,
    create_plan_from_pipeline,
    freeze_plan,
    preflight_plan,
    queue_plan_execution,
    rollback_batch,
    run_pipeline,
)
from .workers import WorkerService
from .workflow_engine import run_template_entry
from .workflow_templates import (
    builtin_templates,
    dump_template,
    parse_template_text,
    processors_from_template,
    template_from_revision,
    validate_template,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.resolved_database_url)
    registry = create_default_registry()
    worker = WorkerService(database, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.config_dir.mkdir(parents=True, exist_ok=True)
        database.create_all()
        if settings.worker_enabled:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        root_path=settings.base_path.rstrip("/"),
    )
    app.state.settings = settings
    app.state.database = database
    app.state.registry = registry
    app.state.worker = worker

    @app.middleware("http")
    async def token_auth(request, call_next):
        if settings.admin_token and request.url.path.startswith("/api"):
            authorization = request.headers.get("authorization", "")
            bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
            supplied = bearer or request.headers.get("x-api-token", "")
            if not secrets.compare_digest(supplied, settings.admin_token):
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=401, content={"detail": "auth.invalid_token"})
        return await call_next(request)

    def session_dependency():
        yield from database.session()

    def require(model: Any, identifier: str, session: Session):
        instance = session.get(model, identifier)
        if not instance:
            raise HTTPException(404, detail=f"{model.__tablename__}.not_found")
        return instance

    @app.exception_handler(DomainError)
    async def domain_error_handler(_, exc: DomainError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"detail": exc.code})

    @app.exception_handler(FileSafetyError)
    async def file_error_handler(_, exc: FileSafetyError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": exc.code})

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "version": settings.version}

    @app.get("/health/ready")
    def health_ready(session: Session = Depends(session_dependency)) -> dict[str, str]:
        session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}

    @app.get("/api/processors")
    def processors() -> list[dict[str, Any]]:
        return [manifest.__dict__ for manifest in registry.manifests()]

    @app.get("/api/junk-rule-packs", response_model=list[JunkRulePack])
    def junk_rule_packs():
        return [junk_pack_dict(DEFAULT_JUNK_PACK)]

    @app.post("/api/junk-rule-packs/validate", response_model=JunkRulePackValidation)
    def validate_junk_rule_pack(payload: JunkRulePack):
        errors: list[str] = []
        warnings: list[str] = []
        seen: set[str] = set()
        for rule in payload.rules:
            if rule.id in seen:
                errors.append(f"junk.duplicate_rule:{rule.id}")
            seen.add(rule.id)
            for pattern in rule.filename_regex:
                try:
                    re.compile(pattern)
                except re.error:
                    errors.append(f"junk.invalid_regex:{rule.id}")
            if not rule.extensions and not rule.filename_contains and not rule.filename_regex and not rule.path_contains and not rule.empty_only:
                warnings.append(f"junk.unbounded_rule:{rule.id}")
        if not payload.rules:
            errors.append("junk.empty_pack")
        return JunkRulePackValidation(
            valid=not errors,
            errors=errors,
            warnings=sorted(set(warnings)),
            rule_count=len(payload.rules),
        )

    @app.get("/api/workflow-templates", response_model=list[WorkflowTemplateV2])
    def list_builtin_templates():
        return builtin_templates()

    @app.post("/api/workflow-templates/validate", response_model=TemplateValidationResult)
    def validate_workflow_template(payload: TemplateTextInput):
        try:
            value = parse_template_text(payload.content, payload.format)
        except ValueError as exc:
            return TemplateValidationResult(valid=False, errors=[str(exc)])
        return validate_template(value, registry, settings.version)

    @app.post("/api/workflow-templates/import", response_model=WorkflowRead, status_code=201)
    def import_workflow_template(
        payload: TemplateImportInput, session: Session = Depends(session_dependency)
    ):
        try:
            value = parse_template_text(payload.content, payload.format)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        validation = validate_template(value, registry, settings.version)
        if not validation.valid or not validation.template:
            raise HTTPException(422, detail={"code": "template.invalid", "errors": validation.errors})
        template = validation.template
        workflow = Workflow(
            name=template.name,
            preset=template.preset,
            review_policy=template.review_policy,
        )
        session.add(workflow)
        session.flush()
        processors = processors_from_template(template)
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=1,
                config={
                    "template": template.model_dump(mode="json"),
                    "processors": [item.model_dump() for item in processors],
                },
            )
        )
        session.commit()
        return workflow

    @app.get("/api/workflow-templates/{workflow_id}/export", response_class=PlainTextResponse)
    def export_workflow_template(
        workflow_id: str,
        format: str = Query("yaml", pattern="^(yaml|json)$"),
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        revision = session.query(WorkflowRevision).filter_by(
            workflow_id=workflow.id, revision=workflow.current_revision
        ).one()
        template = template_from_revision(
            workflow.name, workflow.preset, workflow.review_policy, revision.config
        )
        return PlainTextResponse(
            dump_template(template, format),
            media_type="application/json" if format == "json" else "application/yaml",
        )

    @app.put("/api/workflow-templates/{workflow_id}", response_model=WorkflowRead)
    def update_workflow_template(
        workflow_id: str,
        payload: WorkflowTemplateUpdate,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        validation = validate_template(payload.template.model_dump(mode="json"), registry, settings.version)
        if not validation.valid or not validation.template:
            raise HTTPException(422, detail={"code": "template.invalid", "errors": validation.errors})
        template = validation.template
        workflow.current_revision += 1
        workflow.name = template.name
        workflow.preset = template.preset
        workflow.review_policy = template.review_policy
        processors = processors_from_template(template)
        session.add(WorkflowRevision(
            workflow_id=workflow.id,
            revision=workflow.current_revision,
            config={
                "template": template.model_dump(mode="json"),
                "processors": [item.model_dump() for item in processors],
            },
        ))
        stale_runs = select(PipelineRun.id).where(PipelineRun.workflow_id == workflow.id)
        session.query(Plan).filter(
            Plan.run_id.in_(stale_runs), Plan.status == "draft"
        ).update({"status": "invalidated"}, synchronize_session=False)
        session.commit()
        return workflow

    @app.post(
        "/api/workflow-templates/{workflow_id}/test-rule", response_model=RuleTestResult
    )
    def test_workflow_rule(
        workflow_id: str,
        payload: RuleTestInput,
        session: Session = Depends(session_dependency),
    ):
        require(Workflow, workflow_id, session)
        path = Path(payload.relative_path)
        context = ProcessingContext(
            entry_id="test",
            relative_path=payload.relative_path,
            original_name=path.name,
            parent_path=path.parent.as_posix() if path.parent != Path(".") else "",
            extension=path.suffix.lower(),
            size=payload.size,
            mtime_ns=payload.mtime_ns,
        )
        template = WorkflowTemplateV2(
            name="Rule test",
            stages=[
                WorkflowStage(id="clean", rules=[payload.rule])
            ],
        )
        trace = run_template_entry(template, context, registry)[0]
        return {
            "matched": trace.status != "skipped",
            "status": trace.status,
            "input": trace.input_data,
            "output": trace.output_data,
            "reasons": trace.reasons,
            "warnings": trace.warnings,
        }

    @app.post("/api/sources", response_model=SourceRead, status_code=201)
    def create_source(payload: SourceCreate, session: Session = Depends(session_dependency)):
        root = normalize_root(payload.root_path)
        if settings.source_roots and not any(
            root == allowed.resolve() or root.is_relative_to(allowed.resolve())
            for allowed in settings.source_roots
        ):
            raise HTTPException(400, detail="source.outside_allowed_roots")
        if session.query(Source).filter_by(root_path=str(root)).one_or_none():
            raise HTTPException(409, detail="source.already_exists")
        source = Source(
            name=payload.name,
            root_path=str(root),
            read_only=payload.read_only,
            exclusions=payload.exclusions,
            protected_paths=payload.protected_paths,
            capabilities=probe_capabilities(root, payload.read_only),
        )
        session.add(source)
        session.commit()
        return source

    @app.get("/api/sources", response_model=list[SourceRead])
    def list_sources(session: Session = Depends(session_dependency)):
        return session.query(Source).order_by(Source.name).all()

    @app.get("/api/sources/{source_id}", response_model=SourceRead)
    def get_source(source_id: str, session: Session = Depends(session_dependency)):
        return require(Source, source_id, session)

    @app.patch("/api/sources/{source_id}", response_model=SourceRead)
    def update_source(
        source_id: str, payload: SourceUpdate, session: Session = Depends(session_dependency)
    ):
        source = require(Source, source_id, session)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(source, key, value)
        source.capabilities = probe_capabilities(Path(source.root_path), source.read_only)
        session.commit()
        return source

    @app.delete("/api/sources/{source_id}", status_code=204)
    def delete_source(source_id: str, session: Session = Depends(session_dependency)):
        source = require(Source, source_id, session)
        session.delete(source)
        session.commit()

    @app.post("/api/scans", response_model=ScanRead, status_code=201)
    def create_scan(payload: ScanCreate, session: Session = Depends(session_dependency)):
        source = require(Source, payload.source_id, session)
        job = ScanJob(
            source_id=source.id,
            mode=payload.mode,
            hash_contents=payload.hash_contents,
            status="queued",
        )
        session.add(job)
        session.commit()
        return job

    @app.get("/api/scans", response_model=list[ScanRead])
    def list_scans(session: Session = Depends(session_dependency)):
        return session.query(ScanJob).order_by(ScanJob.created_at.desc()).all()

    @app.get("/api/scans/{scan_id}", response_model=ScanRead)
    def get_scan(scan_id: str, session: Session = Depends(session_dependency)):
        return require(ScanJob, scan_id, session)

    @app.post("/api/scans/{scan_id}/pause", response_model=ScanRead)
    def pause_scan(scan_id: str, session: Session = Depends(session_dependency)):
        job = require(ScanJob, scan_id, session)
        if job.status not in {"queued", "running"}:
            raise HTTPException(409, detail="scan.not_pauseable")
        job.status = "paused" if job.status == "queued" else "pause_requested"
        session.commit()
        return job

    @app.post("/api/scans/{scan_id}/cancel", response_model=ScanRead)
    def cancel_scan(scan_id: str, session: Session = Depends(session_dependency)):
        job = require(ScanJob, scan_id, session)
        if job.status not in {"queued", "running", "paused", "pause_requested"}:
            raise HTTPException(409, detail="scan.not_cancellable")
        job.status = (
            "cancel_requested" if job.status in {"running", "pause_requested"} else "cancelled"
        )
        session.commit()
        return job

    @app.post("/api/scans/{scan_id}/retry", response_model=ScanRead)
    def retry_scan(scan_id: str, session: Session = Depends(session_dependency)):
        job = require(ScanJob, scan_id, session)
        if job.status not in {"failed", "partial", "paused", "cancelled"}:
            raise HTTPException(409, detail="scan.not_retryable")
        job.status = "queued"
        job.completed_at = None
        session.commit()
        return job

    @app.get("/api/files", response_model=list[FileRead])
    def list_files(
        source_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: Session = Depends(session_dependency),
    ):
        return (
            session.query(FileEntry)
            .filter_by(source_id=source_id, active=True)
            .order_by(FileEntry.relative_path)
            .offset(offset)
            .limit(limit)
            .all()
        )

    @app.get("/api/files/page", response_model=FilePage)
    def page_files(
        source_id: str,
        search: str | None = None,
        extension: str | None = None,
        min_size: int | None = Query(default=None, ge=0),
        max_size: int | None = Query(default=None, ge=0),
        include_directories: bool = False,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: Session = Depends(session_dependency),
    ):
        require(Source, source_id, session)
        query = session.query(FileEntry).filter_by(source_id=source_id, active=True)
        if not include_directories:
            query = query.filter_by(is_dir=False)
        if search:
            query = query.filter(FileEntry.relative_path.ilike(f"%{search}%"))
        if extension:
            normalized_extension = extension if extension.startswith(".") else f".{extension}"
            query = query.filter(func.lower(FileEntry.extension) == normalized_extension.lower())
        if min_size is not None:
            query = query.filter(FileEntry.size >= min_size)
        if max_size is not None:
            query = query.filter(FileEntry.size <= max_size)
        total = query.count()
        items = query.order_by(FileEntry.relative_path).offset(offset).limit(limit).all()
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/file-groups", response_model=list[FileGroupRead])
    def list_file_groups(
        source_id: str,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: Session = Depends(session_dependency),
    ):
        require(Source, source_id, session)
        return (
            session.query(FileGroup)
            .filter_by(source_id=source_id)
            .order_by(FileGroup.group_key)
            .offset(offset)
            .limit(limit)
            .all()
        )

    @app.post("/api/workflows", response_model=WorkflowRead, status_code=201)
    def create_workflow(payload: WorkflowCreate, session: Session = Depends(session_dependency)):
        workflow = Workflow(
            name=payload.name, preset=payload.preset, review_policy=payload.review_policy
        )
        session.add(workflow)
        session.flush()
        processors_config = payload.processors or DEFAULT_PROCESSORS
        revision = WorkflowRevision(
            workflow_id=workflow.id,
            revision=1,
            config={"processors": [item.model_dump() for item in processors_config]},
        )
        session.add(revision)
        session.commit()
        return workflow

    @app.get("/api/workflows", response_model=list[WorkflowRead])
    def list_workflows(session: Session = Depends(session_dependency)):
        return session.query(Workflow).order_by(Workflow.name).all()

    @app.get(
        "/api/workflows/{workflow_id}/revisions",
        response_model=list[WorkflowRevisionRead],
    )
    def list_workflow_revisions(
        workflow_id: str, session: Session = Depends(session_dependency)
    ):
        require(Workflow, workflow_id, session)
        return (
            session.query(WorkflowRevision)
            .filter_by(workflow_id=workflow_id)
            .order_by(WorkflowRevision.revision.desc())
            .all()
        )

    @app.get("/api/workflows/{workflow_id}/export", response_model=WorkflowPortable)
    def export_workflow(workflow_id: str, session: Session = Depends(session_dependency)):
        workflow = require(Workflow, workflow_id, session)
        revision = (
            session.query(WorkflowRevision)
            .filter_by(workflow_id=workflow.id, revision=workflow.current_revision)
            .one()
        )
        return {
            "schema_version": 1,
            "name": workflow.name,
            "preset": workflow.preset,
            "review_policy": workflow.review_policy,
            "processors": revision.config.get("processors", []),
        }

    @app.post("/api/workflows/import", response_model=WorkflowRead, status_code=201)
    def import_workflow(payload: WorkflowPortable, session: Session = Depends(session_dependency)):
        registry.validate_order([item.id for item in payload.processors if item.enabled])
        workflow = Workflow(
            name=payload.name,
            preset=payload.preset,
            review_policy=payload.review_policy,
        )
        session.add(workflow)
        session.flush()
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=1,
                config={"processors": [item.model_dump() for item in payload.processors]},
            )
        )
        session.commit()
        return workflow

    @app.get("/api/workflows/{workflow_id}/compare", response_model=WorkflowCompare)
    def compare_workflow_revisions(
        workflow_id: str,
        from_revision: int = Query(ge=1),
        to_revision: int = Query(ge=1),
        session: Session = Depends(session_dependency),
    ):
        require(Workflow, workflow_id, session)
        revisions = (
            session.query(WorkflowRevision)
            .filter(
                WorkflowRevision.workflow_id == workflow_id,
                WorkflowRevision.revision.in_([from_revision, to_revision]),
            )
            .all()
        )
        by_number = {revision.revision: revision for revision in revisions}
        if from_revision not in by_number or to_revision not in by_number:
            raise HTTPException(404, detail="workflow.revision_not_found")
        before = {
            item["id"]: item
            for item in by_number[from_revision].config.get("processors", [])
        }
        after = {
            item["id"]: item for item in by_number[to_revision].config.get("processors", [])
        }
        before_ids, after_ids = set(before), set(after)
        shared = before_ids & after_ids
        return {
            "workflow_id": workflow_id,
            "from_revision": from_revision,
            "to_revision": to_revision,
            "added": sorted(after_ids - before_ids),
            "removed": sorted(before_ids - after_ids),
            "changed": sorted(identifier for identifier in shared if before[identifier] != after[identifier]),
            "unchanged": sorted(identifier for identifier in shared if before[identifier] == after[identifier]),
        }

    @app.post("/api/workflows/{workflow_id}/impact", response_model=WorkflowImpactSummary)
    def workflow_impact(
        workflow_id: str,
        source_id: str,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        source = require(Source, source_id, session)
        run = run_pipeline(session, source, workflow, registry)
        plan = create_plan_from_pipeline(session, run)
        kinds = [operation.kind for operation in plan.operations]
        archive = 0
        for operation in plan.operations:
            if any(reason == "action.archive" for reason in operation.reasons):
                archive += 1
        total = int(run.summary.get("files", 0))
        conflicts = 0
        try:
            preflight_plan(session, plan)
        except (DomainError, FileSafetyError):
            conflicts = 1
        return {
            "workflow_id": workflow_id,
            "source_id": source_id,
            "total": total,
            "rename": kinds.count("rename"),
            "move": kinds.count("move") - archive,
            "archive": archive,
            "quarantine": kinds.count("quarantine"),
            "unchanged": max(0, total - len(plan.operations)),
            "conflicts": conflicts,
            "review": int(plan.summary.get("unresolved_review_count", 0)),
        }

    @app.post("/api/workflows/{workflow_id}/revisions", response_model=WorkflowRead)
    def revise_workflow(
        workflow_id: str,
        payload: WorkflowRevisionCreate,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
        stale_runs = select(PipelineRun.id).where(PipelineRun.workflow_id == workflow.id)
        session.query(Plan).filter(
            Plan.run_id.in_(stale_runs), Plan.status == "draft"
        ).update({"status": "invalidated"}, synchronize_session=False)
        workflow.current_revision += 1
        if payload.review_policy:
            workflow.review_policy = payload.review_policy
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=workflow.current_revision,
                config={"processors": [item.model_dump() for item in payload.processors]},
            )
        )
        session.commit()
        return workflow

    @app.post("/api/pipeline-runs", response_model=PipelineRunRead, status_code=201)
    def create_pipeline_run(
        payload: PipelineRunCreate, session: Session = Depends(session_dependency)
    ):
        source = require(Source, payload.source_id, session)
        workflow = require(Workflow, payload.workflow_id, session)
        return run_pipeline(session, source, workflow, registry)

    @app.get("/api/pipeline-runs", response_model=list[PipelineRunRead])
    def list_pipeline_runs(session: Session = Depends(session_dependency)):
        return session.query(PipelineRun).order_by(PipelineRun.created_at.desc()).all()

    @app.get("/api/pipeline-runs/{run_id}/trace", response_model=list[StageResultRead])
    def pipeline_trace(
        run_id: str,
        file_entry_id: str | None = None,
        session: Session = Depends(session_dependency),
    ):
        query = session.query(StageResult).filter_by(run_id=run_id)
        if file_entry_id:
            query = query.filter_by(file_entry_id=file_entry_id)
        return query.order_by(StageResult.created_at).all()

    @app.get("/api/reviews", response_model=list[ReviewItemRead])
    def reviews(
        run_id: str | None = None,
        limit: int = Query(200, ge=1, le=1000),
        session: Session = Depends(session_dependency),
    ):
        query = session.query(StageResult).filter(StageResult.status.in_(["review", "warning"]))
        if run_id:
            query = query.filter_by(run_id=run_id)
        flagged = query.order_by(StageResult.created_at.desc()).all()
        keys: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for result in flagged:
            key = (result.run_id, result.file_entry_id)
            if key not in seen:
                keys.append(key)
                seen.add(key)
            if len(keys) >= limit:
                break
        items: list[dict[str, Any]] = []
        for item_run_id, file_entry_id in keys:
            entry = session.get(FileEntry, file_entry_id)
            if not entry:
                continue
            results = (
                session.query(StageResult)
                .filter_by(run_id=item_run_id, file_entry_id=file_entry_id)
                .order_by(StageResult.created_at)
                .all()
            )
            latest = results[-1]
            proposed_name = latest.output_data.get("proposed_name") or entry.name
            proposed_parent = latest.output_data.get("proposed_parent")
            if proposed_parent is None:
                proposed_parent = entry.parent_path
            proposed_path = (
                (Path(proposed_parent) / proposed_name).as_posix()
                if proposed_parent
                else proposed_name
            )
            decision = (
                session.query(ReviewDecision)
                .filter_by(run_id=item_run_id, file_entry_id=file_entry_id)
                .one_or_none()
            )
            items.append(
                {
                    "run_id": item_run_id,
                    "file_entry_id": file_entry_id,
                    "relative_path": entry.relative_path,
                    "proposed_relative_path": proposed_path,
                    "confidence": latest.confidence,
                    "reasons": [reason for result in results for reason in result.reasons],
                    "warnings": [warning for result in results for warning in result.warnings],
                    "processors": [result.processor_id for result in results],
                    "decision": decision,
                }
            )
        return items

    @app.put(
        "/api/reviews/{run_id}/{file_entry_id}",
        response_model=ReviewDecisionRead,
    )
    def decide_review(
        run_id: str,
        file_entry_id: str,
        payload: ReviewDecisionUpsert,
        session: Session = Depends(session_dependency),
    ):
        run = require(PipelineRun, run_id, session)
        entry = require(FileEntry, file_entry_id, session)
        if entry.source_id != run.source_id:
            raise HTTPException(400, detail="review.file_outside_run_source")
        flagged = (
            session.query(StageResult)
            .filter_by(run_id=run_id, file_entry_id=file_entry_id)
            .filter(StageResult.status.in_(["review", "warning"]))
            .first()
        )
        if not flagged:
            raise HTTPException(409, detail="review.not_required")
        decision = (
            session.query(ReviewDecision)
            .filter_by(run_id=run_id, file_entry_id=file_entry_id)
            .one_or_none()
        )
        if decision is None:
            decision = ReviewDecision(run_id=run_id, file_entry_id=file_entry_id, action="keep")
            session.add(decision)
        decision.action = payload.action
        decision.target_relative_path = payload.target_relative_path
        decision.note = payload.note
        session.commit()
        return decision

    @app.post("/api/plans", response_model=PlanRead, status_code=201)
    def create_plan(payload: PlanCreate, session: Session = Depends(session_dependency)):
        run = require(PipelineRun, payload.run_id, session)
        return create_plan_from_pipeline(session, run)

    @app.post("/api/plans/manual", response_model=PlanRead, status_code=201)
    def manual_plan(payload: ManualPlanCreate, session: Session = Depends(session_dependency)):
        return create_manual_plan(session, payload)

    @app.get("/api/plans", response_model=list[PlanRead])
    def list_plans(session: Session = Depends(session_dependency)):
        return session.query(Plan).order_by(Plan.created_at.desc()).all()

    @app.post("/api/plans/{plan_id}/freeze", response_model=PlanRead)
    def freeze(plan_id: str, session: Session = Depends(session_dependency)):
        return freeze_plan(session, require(Plan, plan_id, session))

    @app.get("/api/plans/{plan_id}/preflight", response_model=PreflightRead)
    def preflight(plan_id: str, session: Session = Depends(session_dependency)):
        return preflight_plan(session, require(Plan, plan_id, session))

    @app.post("/api/plans/{plan_id}/confirm", response_model=PlanRead)
    def confirm(plan_id: str, session: Session = Depends(session_dependency)):
        return confirm_plan(session, require(Plan, plan_id, session))

    @app.post("/api/batches", response_model=BatchRead, status_code=201)
    def create_batch(plan_id: str, session: Session = Depends(session_dependency)):
        return queue_plan_execution(session, require(Plan, plan_id, session))

    @app.get("/api/batches", response_model=list[BatchRead])
    def list_batches(session: Session = Depends(session_dependency)):
        return session.query(ExecutionBatch).order_by(ExecutionBatch.created_at.desc()).all()

    @app.get("/api/batches/{batch_id}", response_model=BatchRead)
    def get_batch(batch_id: str, session: Session = Depends(session_dependency)):
        return require(ExecutionBatch, batch_id, session)

    @app.post("/api/batches/{batch_id}/pause", response_model=BatchRead)
    def pause_batch(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        if batch.status not in {"queued", "running"}:
            raise HTTPException(409, detail="batch.not_pauseable")
        batch.status = "paused" if batch.status == "queued" else "pause_requested"
        session.commit()
        return batch

    @app.post("/api/batches/{batch_id}/cancel", response_model=BatchRead)
    def cancel_batch(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        if batch.status not in {"queued", "running", "paused", "pause_requested"}:
            raise HTTPException(409, detail="batch.not_cancellable")
        batch.status = (
            "cancel_requested" if batch.status in {"running", "pause_requested"} else "cancelled"
        )
        session.commit()
        return batch

    @app.post("/api/batches/{batch_id}/retry", response_model=BatchRead)
    def retry_batch(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        if batch.status not in {"failed", "paused", "cancelled"}:
            raise HTTPException(409, detail="batch.not_retryable")
        plan = require(Plan, batch.plan_id, session)
        batch.status = "queued"
        batch.failed = 0
        batch.error = None
        batch.completed_at = None
        plan.status = "queued"
        session.commit()
        return batch

    @app.post("/api/batches/{batch_id}/rollback", response_model=BatchRead)
    def rollback(batch_id: str, session: Session = Depends(session_dependency)):
        return rollback_batch(session, require(ExecutionBatch, batch_id, session))

    @app.get("/api/batches/{batch_id}/rollback-preview", response_model=RollbackPreview)
    def rollback_preview(batch_id: str, session: Session = Depends(session_dependency)):
        batch = require(ExecutionBatch, batch_id, session)
        plan = require(Plan, batch.plan_id, session)
        source = require(Source, plan.source_id, session)
        root = normalize_root(source.root_path)
        successful_ids = {
            log.operation_id
            for log in session.query(AuditLog)
            .filter_by(batch_id=batch.id, event="operation.executed", status="success")
            .all()
        }
        items: list[dict[str, Any]] = []
        for operation in reversed(plan.operations):
            if operation.id not in successful_ids:
                continue
            current_relative = operation.target_relative_path
            if operation.kind == "quarantine":
                current_relative = (
                    Path(settings.quarantine_name) / Path(operation.target_relative_path).name
                ).as_posix()
            current = resolve_inside(root, current_relative)
            original = resolve_inside(root, operation.source_relative_path)
            conflict = None
            if not current.exists():
                conflict = "rollback.current_missing"
            elif original.exists():
                conflict = "rollback.target_exists"
            items.append(
                {
                    "operation_id": operation.id,
                    "source_relative_path": current_relative,
                    "target_relative_path": operation.source_relative_path,
                    "ready": conflict is None,
                    "conflict": conflict,
                }
            )
        return {"batch_id": batch.id, "ready": all(item["ready"] for item in items), "operations": items}

    @app.get("/api/history", response_model=list[AuditRead])
    def history(
        limit: int = Query(200, ge=1, le=1000), session: Session = Depends(session_dependency)
    ):
        return session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()

    @app.post("/api/backups")
    def backup(session: Session = Depends(session_dependency)):
        path = create_backup(session, settings)
        return {"status": "completed", "filename": path.name}

    @app.get("/api/backups", response_model=list[BackupRead])
    def list_backups():
        directory = settings.config_dir / "backups"
        if not directory.exists():
            return []
        return [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "created_at": datetime.fromtimestamp(path.stat().st_mtime, UTC),
            }
            for path in sorted(directory.glob("file-curator-*.db"), reverse=True)
            if path.is_file()
        ]

    @app.get("/api/backups/{filename}", response_class=FileResponse)
    def download_backup(filename: str):
        if Path(filename).name != filename:
            raise HTTPException(400, detail="backup.invalid_filename")
        path = settings.config_dir / "backups" / filename
        if not path.is_file():
            raise HTTPException(404, detail="backup.not_found")
        return FileResponse(path, filename=filename, media_type="application/vnd.sqlite3")

    @app.get("/api/diagnostics", response_model=DiagnosticsRead)
    def diagnostics(session: Session = Depends(session_dependency)):
        return {
            "version": settings.version,
            "worker_alive": worker.is_alive if settings.worker_enabled else False,
            "database": Path(database.engine.url.database or "memory").name,
            "config_writable": settings.config_dir.exists()
            and os.access(settings.config_dir, os.W_OK),
            "webhook_configured": bool(settings.webhook_url),
            "counts": {
                "sources": session.query(Source).count(),
                "files": session.query(FileEntry).filter_by(active=True).count(),
                "workflows": session.query(Workflow).count(),
                "plans": session.query(Plan).count(),
                "batches": session.query(ExecutionBatch).count(),
            },
        }

    @app.post("/api/schedules", response_model=ScheduleRead, status_code=201)
    def create_schedule(payload: ScheduleCreate, session: Session = Depends(session_dependency)):
        require(Source, payload.source_id, session)
        schedule = Schedule(
            name=payload.name,
            source_id=payload.source_id,
            enabled=payload.enabled,
            interval_minutes=payload.interval_minutes,
            next_run_at=datetime.now(UTC) + timedelta(minutes=payload.interval_minutes),
        )
        session.add(schedule)
        session.commit()
        return schedule

    @app.get("/api/schedules", response_model=list[ScheduleRead])
    def list_schedules(session: Session = Depends(session_dependency)):
        return session.query(Schedule).order_by(Schedule.name).all()

    @app.patch("/api/schedules/{schedule_id}", response_model=ScheduleRead)
    def update_schedule(
        schedule_id: str,
        payload: ScheduleUpdate,
        session: Session = Depends(session_dependency),
    ):
        schedule = require(Schedule, schedule_id, session)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(schedule, key, value)
        if payload.interval_minutes is not None:
            schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=payload.interval_minutes)
        session.commit()
        return schedule

    @app.delete("/api/schedules/{schedule_id}", status_code=204)
    def delete_schedule(schedule_id: str, session: Session = Depends(session_dependency)):
        session.delete(require(Schedule, schedule_id, session))
        session.commit()

    @app.get("/api/duplicates", response_model=list[DuplicateCandidate])
    def duplicate_candidates(
        source_id: str,
        method: str = Query(
            "normalized_name_size", pattern="^(name_size|normalized_name_size|hash)$"
        ),
        session: Session = Depends(session_dependency),
    ):
        require(Source, source_id, session)
        groups: dict[str, list[FileEntry]] = {}
        entries = (
            session.query(FileEntry).filter_by(source_id=source_id, active=True, is_dir=False).all()
        )
        for entry in entries:
            if method == "hash":
                if not entry.content_hash:
                    continue
                key = entry.content_hash
            elif method == "name_size":
                key = f"{entry.name.casefold()}:{entry.size}"
            else:
                normalized = "".join(
                    character
                    for character in Path(entry.name).stem.casefold()
                    if character.isalnum()
                )
                key = f"{normalized}:{entry.size}"
            groups.setdefault(key, []).append(entry)
        return [
            {
                "key": key,
                "method": method,
                "members": [
                    {
                        "id": entry.id,
                        "relative_path": entry.relative_path,
                        "size": entry.size,
                        "content_hash": entry.content_hash,
                    }
                    for entry in members
                ],
            }
            for key, members in groups.items()
            if len(members) > 1
        ]

    if settings.serve_ui and settings.ui_dir.exists():
        assets = settings.ui_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            requested = settings.ui_dir / path
            if requested.is_file() and settings.ui_dir.resolve() in requested.resolve().parents:
                return FileResponse(requested)
            return FileResponse(settings.ui_dir / "index.html")

    return app


app = create_app()
