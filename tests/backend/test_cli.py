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
    monkeypatch.setattr(cli, "run_migrations", lambda value: None)
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
    monkeypatch.setattr(cli, "run_migrations", lambda value: None)

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2


def test_restore_backup_command_runs_offline(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings(config_dir=tmp_path, serve_ui=False)
    restored = tmp_path / "file-curator.db"
    monkeypatch.setattr(
        sys,
        "argv",
        ["file-curator", "restore-backup", "--backup", "file-curator-test.db"],
    )
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(cli, "run_migrations", lambda value: None)
    monkeypatch.setattr(cli, "restore_backup", lambda value, name: restored)

    cli.main()

    assert capsys.readouterr().out.strip() == f"Restored database: {restored}"


def test_run_migrations_uses_runtime_database(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "alembic.ini"
    config_path.write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    settings = Settings(
        alembic_config=config_path,
        database_url="sqlite:///runtime.db",
        serve_ui=False,
    )
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, path: str):
            captured["path"] = path

        def set_main_option(self, key: str, value: str):
            captured[key] = value

    monkeypatch.setattr(cli, "Config", FakeConfig)
    monkeypatch.setattr(cli, "detect_unstamped_revision", lambda url: None)
    monkeypatch.setattr(cli.command, "upgrade", lambda config, target: captured.update(target=target))

    cli.run_migrations(settings)

    assert captured == {
        "path": str(config_path),
        "sqlalchemy.url": "sqlite:///runtime.db",
        "target": "head",
    }


def test_detects_unstamped_internal_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'unstamped.db').as_posix()}"
    database = cli.Database(database_url)
    database.create_all()

    assert cli.detect_unstamped_revision(database_url) == "0003_scan_content_hash"
