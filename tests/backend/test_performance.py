import time
from pathlib import Path

from file_curator.db import Database, ScanJob, Source
from file_curator.filesystem import scan_source


def test_metadata_scan_smoke_performance(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    for index in range(500):
        (root / f"file-{index:04d}.txt").write_text("x", encoding="utf-8")
    database = Database(f"sqlite:///{(tmp_path / 'performance.db').as_posix()}")
    database.create_all()
    with database.session_factory() as session:
        source = Source(name="Performance", root_path=str(root))
        session.add(source)
        session.flush()
        job = ScanJob(source_id=source.id, mode="full")
        session.add(job)
        session.commit()
        started = time.monotonic()

        scan_source(session, source, job, max_entries=1_000)

        elapsed = time.monotonic() - started
        assert job.status == "completed"
        assert job.scanned_count == 500
        assert elapsed < 10
