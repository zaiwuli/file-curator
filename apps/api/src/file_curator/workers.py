import threading
from datetime import UTC, datetime, timedelta

from .config import Settings
from .db import Database, ExecutionBatch, ScanJob, Schedule, Source
from .filesystem import scan_source
from .services import DomainError, execute_batch


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
                        ScanJob(source_id=schedule.source_id, mode="incremental", status="queued")
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
            except Exception as exc:
                job.status = "failed"
                job.error_count += 1
                job.errors = [*job.errors, {"path": job.cursor or "", "error": type(exc).__name__}]
                session.commit()
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
            return True
