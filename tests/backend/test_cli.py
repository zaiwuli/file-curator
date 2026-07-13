import sys
from pathlib import Path

import pytest

from file_curator import cli
from file_curator.config import Settings


def test_default_command_serves_with_configured_address(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path, host="127.0.0.9", port=8123, serve_ui=False)
    calls: list[dict] = []
    monkeypatch.setattr(sys, "argv", ["file-curator"])
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(cli, "create_app", lambda value: ("app", value))
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append({"app": app, **kwargs}))

    cli.main()

    assert calls == [
        {
            "app": ("app", settings),
            "host": "127.0.0.9",
            "port": 8123,
            "workers": 1,
            "log_level": "info",
        }
    ]


def test_serve_rejects_multiple_sqlite_workers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["file-curator", "serve"])
    monkeypatch.setattr(
        cli,
        "Settings",
        lambda: Settings(config_dir=tmp_path, workers=2, serve_ui=False),
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
