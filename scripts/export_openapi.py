from __future__ import annotations

import json
from pathlib import Path

from file_curator.config import Settings
from file_curator.main import create_app


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "packages" / "contracts" / "openapi.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    app = create_app(
        Settings(
            database_url="sqlite:///:memory:",
            serve_ui=False,
            worker_enabled=False,
        )
    )
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

