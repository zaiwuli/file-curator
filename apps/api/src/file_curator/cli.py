import argparse

import uvicorn

from .config import Settings
from .db import Database
from .main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="file-curator")
    parser.add_argument("command", choices=["serve", "init-db"], nargs="?", default="serve")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    settings = Settings()
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
