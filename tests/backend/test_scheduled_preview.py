from datetime import UTC, datetime, timedelta
from pathlib import Path

from file_curator.config import Settings
from file_curator.db import Database, Plan, ScanJob, Schedule, Source, Workflow, WorkflowRevision
from file_curator.schemas import RuleCard, WorkflowAction, WorkflowStage, WorkflowTemplateV2
from file_curator.workers import WorkerService


def test_scheduled_scan_generates_draft_preview(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "Example.MP4").write_bytes(b"video")
    settings = Settings(
        config_dir=tmp_path / "config",
        database_url=f"sqlite:///{(tmp_path / 'scheduled.db').as_posix()}",
        serve_ui=False,
    )
    database = Database(settings.resolved_database_url)
    database.create_all()
    with database.session_factory() as session:
        source = Source(name="Scheduled source", root_path=str(root))
        workflow = Workflow(name="Scheduled workflow")
        session.add_all([source, workflow])
        session.flush()
        session.add(
            WorkflowRevision(
                workflow_id=workflow.id,
                revision=1,
                config={
                    "template": WorkflowTemplateV2(
                        name="Scheduled workflow",
                        stages=[
                            WorkflowStage(
                                id="classify",
                                rules=[
                                    RuleCard(
                                        id="detect.duplicates",
                                        name="Detect duplicates",
                                        actions=[
                                            WorkflowAction(
                                                kind="run_processor",
                                                options={
                                                    "processor_id": "detect_duplicates",
                                                    "method": "hash",
                                                },
                                            )
                                        ],
                                    )
                                ],
                            )
                        ],
                    ).model_dump(mode="json"),
                    "processors": [
                        {"id": "detect_duplicates", "enabled": True, "options": {}}
                    ]
                },
            )
        )
        session.add(
            Schedule(
                name="Preview schedule",
                source_id=source.id,
                workflow_id=workflow.id,
                generate_preview=True,
                interval_minutes=60,
                next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        session.commit()

    worker = WorkerService(database, settings)
    worker._tick_schedules()
    with database.session_factory() as session:
        job = session.query(ScanJob).one()
        assert job.post_workflow_id is not None
        assert job.hash_contents is True

    assert worker._run_scan() is True
    with database.session_factory() as session:
        plan = session.query(Plan).one()
        assert plan.status == "draft"
