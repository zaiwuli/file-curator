import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_SRC = Path(__file__).parents[2] / "apps" / "api" / "src"
sys.path.insert(0, str(API_SRC))

from file_curator.config import Settings  # noqa: E402
from file_curator.main import create_app  # noqa: E402


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    return root


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        config_dir=tmp_path / "config",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        serve_ui=False,
        execution_batch_size=100,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
