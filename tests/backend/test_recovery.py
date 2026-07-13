import json
import sqlite3
from pathlib import Path

from file_curator.config import Settings
from file_curator.db import Database, ScanJob, Source
from file_curator.services import restore_backup
from file_curator.workers import WorkerService


def test_restore_backup_replaces_offline_database(tmp_path: Path) -> None:
    config = tmp_path / "config"
    backups = config / "backups"
    backups.mkdir(parents=True)
    backup = backups / "file-curator-test.db"
    target = config / "file-curator.db"
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('backup')")
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE stale (value TEXT)")
    settings = Settings(config_dir=config, database_url=f"sqlite:///{target.as_posix()}")

    restored = restore_backup(settings, backup.name)

    assert restored == target
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("backup",)


def test_webhook_notification_contains_only_job_summary(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    def open_request(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    settings = Settings(
        database_url="sqlite:///:memory:",
        webhook_url="https://example.invalid/hook",
        webhook_timeout=2,
    )
    worker = WorkerService(Database(settings.resolved_database_url), settings)

    worker._notify("scan.finished", {"scan_id": "scan-1", "status": "completed"})

    assert captured == {
        "body": {"event": "scan.finished", "scan_id": "scan-1", "status": "completed"},
        "timeout": 2.0,
    }


def test_worker_recovers_interrupted_scan_to_queue(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}")
    database.create_all()
    with database.session_factory() as session:
        source = Source(name="Recovery", root_path=str(tmp_path))
        session.add(source)
        session.flush()
        job = ScanJob(source_id=source.id, mode="full", status="running")
        session.add(job)
        session.commit()
        job_id = job.id
    worker = WorkerService(database, Settings(database_url=str(database.engine.url)))

    worker._recover_interrupted()

    with database.session_factory() as session:
        assert session.get(ScanJob, job_id).status == "queued"
