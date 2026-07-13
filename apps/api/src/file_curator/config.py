from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILE_CURATOR_", extra="ignore")

    app_name: str = "File Curator"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1
    log_level: str = "info"
    config_dir: Path = Path("./data")
    database_url: str | None = None
    source_roots: list[Path] = []
    max_scan_entries: int = 1_000_000
    execution_batch_size: int = 20
    quarantine_name: str = ".file-curator-quarantine"
    serve_ui: bool = True
    ui_dir: Path = Path("./static")
    base_path: str = ""
    admin_token: str | None = None
    worker_enabled: bool = True
    worker_poll_seconds: float = 0.25
    webhook_url: str | None = None
    webhook_timeout: float = 5.0

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.config_dir / 'file-curator.db').resolve().as_posix()}"
