from pathlib import Path

from fastapi.testclient import TestClient

from file_curator.config import Settings
from file_curator.main import create_app


def test_admin_token_protects_api_but_not_health(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            config_dir=tmp_path / "config",
            database_url=f"sqlite:///{(tmp_path / 'auth.db').as_posix()}",
            admin_token="secret-token",
            worker_enabled=False,
            serve_ui=False,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/sources").status_code == 401
        authorized = client.get("/api/sources", headers={"Authorization": "Bearer secret-token"})
        assert authorized.status_code == 200


def test_queued_scan_can_pause_retry_and_cancel(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    app = create_app(
        Settings(
            config_dir=tmp_path / "config",
            database_url=f"sqlite:///{(tmp_path / 'controls.db').as_posix()}",
            worker_enabled=False,
            serve_ui=False,
        )
    )
    with TestClient(app) as client:
        source = client.post("/api/sources", json={"name": "Media", "root_path": str(media)}).json()
        scan = client.post("/api/scans", json={"source_id": source["id"]}).json()
        assert client.post(f"/api/scans/{scan['id']}/pause").json()["status"] == "paused"
        assert client.post(f"/api/scans/{scan['id']}/retry").json()["status"] == "queued"
        assert client.post(f"/api/scans/{scan['id']}/cancel").json()["status"] == "cancelled"
