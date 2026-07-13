import argparse

import uvicorn

from .config import Settings
from .db import Database
from .main import create_app
from .services import restore_backup


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
    if args.command == "init-db":
        database = Database(settings.resolved_database_url)
        database.create_all()
        return
    if args.command == "restore-backup":
        if not args.backup:
            parser.error("--backup is required for restore-backup")
        restored = restore_backup(settings, args.backup)
        print(f"Restored database: {restored}")
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
