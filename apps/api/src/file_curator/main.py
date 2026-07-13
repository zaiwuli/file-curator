import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import Settings
from .db import (
    AuditLog,
    Database,
    ExecutionBatch,
    FileEntry,
    PipelineRun,
    Plan,
    ScanJob,
    Schedule,
    Source,
    StageResult,
    Workflow,
    WorkflowRevision,
)
from .filesystem import FileSafetyError, normalize_root, probe_capabilities
from .processors import create_default_registry
from .schemas import (
    AuditRead,
    BatchRead,
    DuplicateCandidate,
    FileRead,
    ManualPlanCreate,
    PipelineRunCreate,
    PipelineRunRead,
    PlanCreate,
    PlanRead,
    ScanCreate,
    ScanRead,
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
    SourceCreate,
    SourceRead,
    SourceUpdate,
    StageResultRead,
    WorkflowCreate,
    WorkflowRead,
    WorkflowRevisionCreate,
)
from .services import (
    DEFAULT_PROCESSORS,
    DomainError,
    confirm_plan,
    create_backup,
    create_manual_plan,
    create_plan_from_pipeline,
    freeze_plan,
    queue_plan_execution,
    rollback_batch,
    run_pipeline,
)
from .workers import WorkerService


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
        job = ScanJob(source_id=source.id, mode=payload.mode, status="queued")
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

    @app.post("/api/workflows/{workflow_id}/revisions", response_model=WorkflowRead)
    def revise_workflow(
        workflow_id: str,
        payload: WorkflowRevisionCreate,
        session: Session = Depends(session_dependency),
    ):
        workflow = require(Workflow, workflow_id, session)
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

    @app.get("/api/reviews", response_model=list[StageResultRead])
    def reviews(
        run_id: str | None = None,
        limit: int = Query(200, ge=1, le=1000),
        session: Session = Depends(session_dependency),
    ):
        query = session.query(StageResult).filter(StageResult.status.in_(["review", "warning"]))
        if run_id:
            query = query.filter_by(run_id=run_id)
        return query.order_by(StageResult.created_at.desc()).limit(limit).all()

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

    @app.get("/api/history", response_model=list[AuditRead])
    def history(
        limit: int = Query(200, ge=1, le=1000), session: Session = Depends(session_dependency)
    ):
        return session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()

    @app.post("/api/backups")
    def backup(session: Session = Depends(session_dependency)):
        path = create_backup(session, settings)
        return {"status": "completed", "filename": path.name}

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
