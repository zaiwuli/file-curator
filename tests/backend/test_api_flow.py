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
    rollback = client.post(f"/api/batches/{batch['id']}/rollback")
    assert rollback.status_code == 200, rollback.text
    assert original.exists() and not renamed.exists()


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
    updated = client.patch(f"/api/schedules/{schedule_id}", json={"enabled": False})
    assert updated.json()["enabled"] is False
    assert client.delete(f"/api/schedules/{schedule_id}").status_code == 204
