import json
import threading
import urllib.request
from datetime import UTC, datetime, timedelta

from .config import Settings
from .db import Database, ExecutionBatch, ScanJob, Schedule, Source, Workflow
from .filesystem import scan_source
from .processors import create_default_registry
from .services import (
    DomainError,
    create_plan_from_pipeline,
    execute_batch,
    get_revision,
    run_pipeline,
)
from .workflow_templates import scan_requirements, template_from_revision


class WorkerService:
    """Single-process durable worker for the SQLite deployment profile."""

    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._recover_interrupted()
        self._thread = threading.Thread(target=self._run, name="file-curator-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._stop.wait(0)

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _recover_interrupted(self) -> None:
        with self.database.session_factory() as session:
            for job in session.query(ScanJob).filter_by(status="running").all():
                job.status = "queued"
            for batch in session.query(ExecutionBatch).filter_by(status="running").all():
                batch.status = "queued"
            session.commit()

    def _notify(self, event: str, payload: dict[str, object]) -> None:
        if not self.settings.webhook_url:
            return
        body = json.dumps({"event": event, **payload}).encode("utf-8")
        request = urllib.request.Request(
            self.settings.webhook_url,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.webhook_timeout):
                pass
        except (OSError, ValueError):
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick_schedules()
                if not self._run_scan():
                    self._run_batch()
            except Exception:
                # Individual jobs persist their errors; the worker must remain available.
                pass
            self._stop.wait(self.settings.worker_poll_seconds)

    def _tick_schedules(self) -> None:
        now = datetime.now(UTC)
        with self.database.session_factory() as session:
            due = (
                session.query(Schedule)
                .filter(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
                .all()
            )
            for schedule in due:
                requirements = {"hash_contents": False, "inspect_small_text": False}
                if schedule.generate_preview and schedule.workflow_id:
                    workflow = session.get(Workflow, schedule.workflow_id)
                    if workflow:
                        template = template_from_revision(
                            workflow.name,
                            workflow.preset,
                            workflow.review_policy,
                            get_revision(session, workflow).config,
                        )
                        requirements = scan_requirements(template)
                active = (
                    session.query(ScanJob)
                    .filter(
                        ScanJob.source_id == schedule.source_id,
                        ScanJob.status.in_(["queued", "running"]),
                    )
                    .first()
                )
                if not active:
                    session.add(
                        ScanJob(
                            source_id=schedule.source_id,
                            mode="incremental",
                            status="queued",
                            hash_contents=requirements["hash_contents"],
                            inspect_small_text=requirements["inspect_small_text"],
                            post_workflow_id=(
                                schedule.workflow_id if schedule.generate_preview else None
                            ),
                        )
                    )
                schedule.last_run_at = now
                schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
            session.commit()

    def _run_scan(self) -> bool:
        with self.database.session_factory() as session:
            job = (
                session.query(ScanJob)
                .filter_by(status="queued")
                .order_by(ScanJob.created_at)
                .first()
            )
            if not job:
                return False
            source = session.get(Source, job.source_id)
            if not source:
                job.status = "failed"
                job.errors = [{"path": "", "error": "source.not_found"}]
                session.commit()
                return True
            job.scanned_count = 0
            job.error_count = 0
            job.errors = []
            job.cursor = None
            job.status = "running"
            session.commit()

            def control() -> str:
                session.refresh(job)
                return job.status

            try:
                scan_source(session, source, job, self.settings.max_scan_entries, control)
                if job.status == "completed" and job.post_workflow_id:
                    workflow = session.get(Workflow, job.post_workflow_id)
                    if workflow:
                        run = run_pipeline(
                            session, source, workflow, create_default_registry()
                        )
                        create_plan_from_pipeline(session, run)
            except Exception as exc:
                job.status = "failed"
                job.error_count += 1
                job.errors = [*job.errors, {"path": job.cursor or "", "error": type(exc).__name__}]
                session.commit()
            self._notify(
                "scan.finished",
                {
                    "scan_id": job.id,
                    "source_id": job.source_id,
                    "status": job.status,
                    "scanned_count": job.scanned_count,
                    "error_count": job.error_count,
                },
            )
            return True

    def _run_batch(self) -> bool:
        with self.database.session_factory() as session:
            batch = (
                session.query(ExecutionBatch)
                .filter_by(status="queued")
                .order_by(ExecutionBatch.created_at)
                .first()
            )
            if not batch:
                return False
            try:
                execute_batch(session, batch, self.settings)
            except Exception as exc:
                batch.status = "failed"
                batch.error = exc.code if isinstance(exc, DomainError) else type(exc).__name__
                session.commit()
            if batch.status in {"completed", "failed", "paused", "cancelled"}:
                self._notify(
                    "batch.finished",
                    {
                        "batch_id": batch.id,
                        "plan_id": batch.plan_id,
                        "status": batch.status,
                        "succeeded": batch.succeeded,
                        "failed": batch.failed,
                    },
                )
            return True
