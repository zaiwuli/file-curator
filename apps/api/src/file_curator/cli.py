import argparse

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from .config import Settings
from .db import Database
from .main import create_app
from .services import restore_backup


def detect_unstamped_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "alembic_version" in tables or "sources" not in tables:
            return None
        scan_columns = {column["name"] for column in inspector.get_columns("scan_jobs")}
        if "review_decisions" in tables and "hash_contents" in scan_columns:
            return "0003_scan_content_hash"
        if "review_decisions" in tables:
            return "0002_review_decisions"
        return "0001_initial"
    finally:
        engine.dispose()


def run_migrations(settings: Settings) -> None:
    if settings.alembic_config is None or not settings.alembic_config.is_file():
        return
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    config = Config(str(settings.alembic_config))
    config.set_main_option("sqlalchemy.url", settings.resolved_database_url)
    unstamped = detect_unstamped_revision(settings.resolved_database_url)
    if unstamped:
        command.stamp(config, unstamped)
    command.upgrade(config, "head")


def main() -> None:
    parser = argparse.ArgumentParser(prog="file-curator")
    parser.add_argument(
        "command", choices=["serve", "init-db", "restore-backup"], nargs="?", default="serve"
    )
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--backup")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "restore-backup":
        if not args.backup:
            parser.error("--backup is required for restore-backup")
        restored = restore_backup(settings, args.backup)
        print(f"Restored database: {restored}")
        return
    run_migrations(settings)
    if args.command == "init-db":
        database = Database(settings.resolved_database_url)
        database.create_all()
        return
    if settings.workers != 1:
        parser.error("FILE_CURATOR_WORKERS must be 1 when using the SQLite task worker")
    uvicorn.run(
        create_app(settings),
        host=args.host or settings.host,
        port=args.port or settings.port,
        workers=1,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
