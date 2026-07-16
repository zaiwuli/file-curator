import sqlite3
import time
from pathlib import Path


def wait_for(client, path: str, terminal: set[str], timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(path).json()
        if payload["status"] in terminal:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {path}")


def create_source_and_scan(client, media_root: Path) -> tuple[str, dict]:
    response = client.post("/api/sources", json={"name": "Media", "root_path": str(media_root)})
    assert response.status_code == 201, response.text
    source_id = response.json()["id"]
    scan = client.post("/api/scans", json={"source_id": source_id, "mode": "full"})
    assert scan.status_code == 201, scan.text
    completed = wait_for(
        client, f"/api/scans/{scan.json()['id']}", {"completed", "failed", "partial"}
    )
    return source_id, completed


def test_health_and_source_scan(client, media_root: Path) -> None:
    (media_root / "A.txt").write_text("hello", encoding="utf-8")
    source_id, scan = create_source_and_scan(client, media_root)
    assert client.get("/health/live").json()["status"] == "ok"
    assert scan["status"] == "completed"
    files = client.get("/api/files", params={"source_id": source_id}).json()
    assert [item["relative_path"] for item in files] == ["A.txt"]


def test_pipeline_plan_execute_and_rollback(client, media_root: Path) -> None:
    original = media_root / "www.site@ABC-123   title.MP4"
    original.write_bytes(b"test-content")
    source_id, _ = create_source_and_scan(client, media_root)
    workflow_response = client.post(
        "/api/workflows",
        json={
            "name": "Rename cleanly",
            "preset": "rename_only",
            "processors": [
                {
                    "id": "normalize_name",
                    "enabled": True,
                    "options": {"remove_prefixes": ["www.site@"]},
                }
            ],
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    run_response = client.post(
        "/api/pipeline-runs",
        json={"source_id": source_id, "workflow_id": workflow_response.json()["id"]},
    )
    assert run_response.status_code == 201, run_response.text
    plan_response = client.post("/api/plans", json={"run_id": run_response.json()["id"]})
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    assert plan["operations"][0]["target_relative_path"] == "ABC-123 title.mp4"
    plan_id = plan["id"]
    preflight = client.get(f"/api/plans/{plan_id}/preflight")
    assert preflight.json() == {"status": "ready", "operation_count": 1}
    assert client.post(f"/api/plans/{plan_id}/freeze").status_code == 200
    assert client.post(f"/api/plans/{plan_id}/confirm").status_code == 200
    batch_response = client.post("/api/batches", params={"plan_id": plan_id})
    assert batch_response.status_code == 201, batch_response.text
    batch = wait_for(
        client,
        f"/api/batches/{batch_response.json()['id']}",
        {"completed", "failed"},
    )
    renamed = media_root / "ABC-123 title.mp4"
    assert renamed.exists() and not original.exists()
    indexed = client.get("/api/files", params={"source_id": source_id}).json()
    assert [item["relative_path"] for item in indexed] == ["ABC-123 title.mp4"]
    rollback_preview = client.get(f"/api/batches/{batch['id']}/rollback-preview").json()
    assert rollback_preview["ready"] is True
    assert rollback_preview["operations"][0]["ready"] is True
    rollback = client.post(f"/api/batches/{batch['id']}/rollback")
    assert rollback.status_code == 200, rollback.text
    assert original.exists() and not renamed.exists()
    indexed = client.get("/api/files", params={"source_id": source_id}).json()
    assert [item["relative_path"] for item in indexed] == [original.name]


def test_freeze_rejects_extension_change(client, media_root: Path) -> None:
    original = media_root / "sample.txt"
    original.write_text("x", encoding="utf-8")
    source_id, _ = create_source_and_scan(client, media_root)
    workflow = client.post("/api/workflows", json={"name": "Manual"}).json()
    run = client.post(
        "/api/pipeline-runs", json={"source_id": source_id, "workflow_id": workflow["id"]}
    ).json()
    plan = client.post(
        "/api/plans/manual",
        json={
            "run_id": run["id"],
            "operations": [
                {
                    "kind": "rename",
                    "source_relative_path": "sample.txt",
                    "target_relative_path": "sample.exe",
                }
            ],
        },
    ).json()
    response = client.post(f"/api/plans/{plan['id']}/freeze")
    assert response.status_code == 400
    assert response.json()["detail"] == "operation.extension_changed"


def test_directory_move_updates_and_rolls_back_index(client, media_root: Path) -> None:
    folder = media_root / "Folder.v1"
    folder.mkdir()
    (folder / "movie.mp4").write_bytes(b"content")
    source_id, _ = create_source_and_scan(client, media_root)
    workflow = client.post("/api/workflows", json={"name": "Directory move"}).json()
    run = client.post(
        "/api/pipeline-runs", json={"source_id": source_id, "workflow_id": workflow["id"]}
    ).json()
    plan = client.post(
        "/api/plans/manual",
        json={
            "run_id": run["id"],
            "operations": [
                {
                    "kind": "move",
                    "source_relative_path": "Folder.v1",
                    "target_relative_path": "Archive/Folder cleaned",
                }
            ],
        },
    ).json()
    client.post(f"/api/plans/{plan['id']}/freeze")
    client.post(f"/api/plans/{plan['id']}/confirm")
    batch = client.post("/api/batches", params={"plan_id": plan["id"]}).json()
    result = wait_for(client, f"/api/batches/{batch['id']}", {"completed", "failed"})

    assert result["status"] == "completed"
    indexed = client.get("/api/files", params={"source_id": source_id}).json()
    assert {item["relative_path"] for item in indexed} == {
        "Archive/Folder cleaned",
        "Archive/Folder cleaned/movie.mp4",
    }

    rollback = client.post(f"/api/batches/{batch['id']}/rollback")
    assert rollback.status_code == 200, rollback.text
    indexed = client.get("/api/files", params={"source_id": source_id}).json()
    assert {item["relative_path"] for item in indexed} == {
        "Folder.v1",
        "Folder.v1/movie.mp4",
    }


def test_schedule_and_duplicate_candidates(client, media_root: Path) -> None:
    (media_root / "Copy One.txt").write_text("same", encoding="utf-8")
    (media_root / "copy-one.txt").write_text("same", encoding="utf-8")
    source_id, _ = create_source_and_scan(client, media_root)
    duplicates = client.get(
        "/api/duplicates",
        params={"source_id": source_id, "method": "normalized_name_size"},
    )
    assert duplicates.status_code == 200
    assert len(duplicates.json()) == 1
    schedule = client.post(
        "/api/schedules",
        json={"name": "Nightly", "source_id": source_id, "interval_minutes": 60},
    )
    assert schedule.status_code == 201
    schedule_id = schedule.json()["id"]
    assert schedule.json()["generate_preview"] is False
    workflow = client.post(
        "/api/workflows",
        json={"name": "Scheduled preview", "processors": [{"id": "normalize_name"}]},
    ).json()
    preview_schedule = client.post(
        "/api/schedules",
        json={
            "name": "Nightly preview",
            "source_id": source_id,
            "workflow_id": workflow["id"],
            "generate_preview": True,
            "interval_minutes": 60,
        },
    )
    assert preview_schedule.status_code == 201, preview_schedule.text
    assert preview_schedule.json()["workflow_id"] == workflow["id"]
    invalid = client.post(
        "/api/schedules",
        json={"name": "Invalid preview", "source_id": source_id, "generate_preview": True},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "schedule.workflow_required"
    updated = client.patch(f"/api/schedules/{schedule_id}", json={"enabled": False})
    assert updated.json()["enabled"] is False
    assert client.delete(f"/api/schedules/{schedule_id}").status_code == 204


def test_workflow_capability_manifest_exposes_ui_schemas(client) -> None:
    response = client.get("/api/workflow-capabilities")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["schema_version"] == 1
    actions = {item["kind"]: item for item in manifest["actions"]}
    assert actions["clean_name"]["option_schema"]["remove_words"]["control"] == "tags"
    processors = {item["id"]: item for item in manifest["processors"]}
    assert processors["detect_junk"]["option_schema"]["filename_contains"]["title_key"] == "workflow.junk.keywords"


def test_review_decisions_gate_and_override_plan_operations(client, media_root: Path) -> None:
    (media_root / "prefix-Example.MP4").write_bytes(b"content")
    source_id, _ = create_source_and_scan(client, media_root)
    workflow = client.post(
        "/api/workflows",
        json={
            "name": "Review required",
            "processors": [
                {
                    "id": "normalize_name",
                    "options": {"remove_prefixes": ["prefix-"]},
                },
                {
                    "id": "target_template",
                    "options": {"parent_template": "{missing_field}"},
                },
            ],
        },
    ).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source_id, "workflow_id": workflow["id"]},
    ).json()
    reviews = client.get("/api/reviews", params={"run_id": run["id"]}).json()
    assert len(reviews) == 1
    item = reviews[0]
    assert item["relative_path"] == "prefix-Example.MP4"
    assert item["proposed_relative_path"] == "Example.mp4"
    assert item["decision"] is None

    unresolved_plan = client.post("/api/plans", json={"run_id": run["id"]}).json()
    assert unresolved_plan["operations"] == []
    assert unresolved_plan["summary"]["unresolved_review_count"] == 1

    accepted = client.put(
        f"/api/reviews/{run['id']}/{item['file_entry_id']}",
        json={"action": "accept"},
    )
    assert accepted.status_code == 200, accepted.text
    accepted_plan = client.post("/api/plans", json={"run_id": run["id"]}).json()
    assert accepted_plan["operations"][0]["target_relative_path"] == "Example.mp4"

    overridden = client.put(
        f"/api/reviews/{run['id']}/{item['file_entry_id']}",
        json={"action": "override", "target_relative_path": "Reviewed/Example.mp4"},
    )
    assert overridden.status_code == 200, overridden.text
    override_plan = client.post("/api/plans", json={"run_id": run["id"]}).json()
    operation = override_plan["operations"][0]
    assert operation["kind"] == "move"
    assert operation["target_relative_path"] == "Reviewed/Example.mp4"
    assert "review.override" in operation["reasons"]

    kept = client.put(
        f"/api/reviews/{run['id']}/{item['file_entry_id']}",
        json={"action": "keep"},
    )
    assert kept.status_code == 200, kept.text
    kept_plan = client.post("/api/plans", json={"run_id": run["id"]}).json()
    assert kept_plan["operations"] == []
    assert kept_plan["summary"]["kept_count"] == 1


def test_file_browser_groups_and_workflow_portability(client, media_root: Path) -> None:
    (media_root / "Movie (1).mkv").write_bytes(b"video")
    (media_root / "Movie (2).srt").write_bytes(b"subtitle")
    (media_root / "notes.txt").write_text("notes", encoding="utf-8")
    source_id, _ = create_source_and_scan(client, media_root)

    page = client.get(
        "/api/files/page",
        params={"source_id": source_id, "search": "movie", "extension": "mkv"},
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["relative_path"] == "Movie (1).mkv"

    workflow = client.post(
        "/api/workflows",
        json={"name": "Portable", "processors": [{"id": "extract_sequence"}]},
    ).json()
    client.post(
        f"/api/workflows/{workflow['id']}/revisions",
        json={
            "processors": [
                {"id": "extract_sequence", "enabled": True},
                {"id": "normalize_name", "enabled": True},
            ]
        },
    )
    revisions = client.get(f"/api/workflows/{workflow['id']}/revisions").json()
    assert [item["revision"] for item in revisions] == [2, 1]
    comparison = client.get(
        f"/api/workflows/{workflow['id']}/compare",
        params={"from_revision": 1, "to_revision": 2},
    ).json()
    assert comparison["added"] == ["normalize_name"]
    assert comparison["unchanged"] == ["extract_sequence"]

    restored = client.post(f"/api/workflows/{workflow['id']}/restore/1")
    assert restored.status_code == 200, restored.text
    assert restored.json()["current_revision"] == 3
    revisions = client.get(f"/api/workflows/{workflow['id']}/revisions").json()
    assert [item["revision"] for item in revisions] == [3, 2, 1]

    exported = client.get(f"/api/workflows/{workflow['id']}/export").json()
    assert [item["id"] for item in exported["processors"]] == ["extract_sequence"]
    exported["name"] = "Imported copy"
    imported = client.post("/api/workflows/import", json=exported)
    assert imported.status_code == 201, imported.text
    assert imported.json()["name"] == "Imported copy"

    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source_id, "workflow_id": workflow["id"]},
    )
    assert run.status_code == 201, run.text
    groups = client.get("/api/file-groups", params={"source_id": source_id}).json()
    assert len(groups) == 1
    assert len(groups[0]["member_ids"]) == 2


def test_execution_continues_across_bounded_chunks(client, media_root: Path) -> None:
    for index in range(3):
        (media_root / f"before-{index}.txt").write_text(str(index), encoding="utf-8")
    source_id, _ = create_source_and_scan(client, media_root)
    workflow = client.post("/api/workflows", json={"name": "Chunked"}).json()
    run = client.post(
        "/api/pipeline-runs",
        json={"source_id": source_id, "workflow_id": workflow["id"]},
    ).json()
    plan = client.post(
        "/api/plans/manual",
        json={
            "run_id": run["id"],
            "operations": [
                {
                    "kind": "rename",
                    "source_relative_path": f"before-{index}.txt",
                    "target_relative_path": f"after-{index}.txt",
                }
                for index in range(3)
            ],
        },
    ).json()
    assert client.post(f"/api/plans/{plan['id']}/freeze").status_code == 200
    assert client.post(f"/api/plans/{plan['id']}/confirm").status_code == 200
    client.app.state.settings.execution_batch_size = 1
    batch = client.post("/api/batches", params={"plan_id": plan["id"]}).json()
    completed = wait_for(client, f"/api/batches/{batch['id']}", {"completed", "failed"})
    assert completed["status"] == "completed"
    assert completed["succeeded"] == 3
    assert all((media_root / f"after-{index}.txt").exists() for index in range(3))


def test_online_backup_is_a_readable_sqlite_database(client) -> None:
    response = client.post("/api/backups")
    assert response.status_code == 200, response.text
    backup_path = (
        client.app.state.settings.config_dir / "backups" / response.json()["filename"]
    )
    with sqlite3.connect(backup_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sources'"
        ).fetchone()
    assert table == ("sources",)
    backups = client.get("/api/backups").json()
    assert backups[0]["filename"] == response.json()["filename"]
    assert client.get(f"/api/backups/{backups[0]['filename']}").status_code == 200
    diagnostics = client.get("/api/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["config_writable"] is True


def test_content_hashing_is_opt_in_and_invalidated_on_change(client, media_root: Path) -> None:
    (media_root / "first.bin").write_bytes(b"same-content")
    (media_root / "second.bin").write_bytes(b"same-content")
    source = client.post(
        "/api/sources", json={"name": "Hashes", "root_path": str(media_root)}
    ).json()
    scan = client.post(
        "/api/scans",
        json={"source_id": source["id"], "mode": "full", "hash_contents": True},
    ).json()
    completed = wait_for(client, f"/api/scans/{scan['id']}", {"completed", "failed"})
    assert completed["status"] == "completed"
    duplicates = client.get(
        "/api/duplicates", params={"source_id": source["id"], "method": "hash"}
    ).json()
    assert len(duplicates) == 1

    (media_root / "second.bin").write_bytes(b"different-and-longer")
    incremental = client.post(
        "/api/scans",
        json={"source_id": source["id"], "mode": "incremental"},
    ).json()
    wait_for(client, f"/api/scans/{incremental['id']}", {"completed", "failed"})
    duplicates = client.get(
        "/api/duplicates", params={"source_id": source["id"], "method": "hash"}
    ).json()
    assert duplicates == []
