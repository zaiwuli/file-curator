# File Curator

File Curator is a local-first file organization workbench. It indexes filesystem metadata, runs deterministic and explainable processors, previews virtual paths, and changes real files only through a frozen and confirmed plan.

The default preset is **Rename Only** with a **Balanced** review policy. Permanent deletion and cross-source copying are intentionally unsupported.

## Safety model

```text
source -> metadata scan -> workflow revision -> pipeline trace -> draft plan
       -> review -> frozen plan -> confirmation -> execution -> verification
       -> audit history / rollback
```

- Scanning and processing use metadata stored in SQLite; draft operations do not touch source files.
- A plan records expected size and modification time before it can be frozen.
- Execution validates path boundaries, source changes, extension preservation, conflicts, and overwrite risk.
- Rename, same-source move, quarantine, and rollback are journaled. There is no permanent delete operation.
- Internal code, API contracts, logs, and error codes are English. UI strings are localized separately.

## Repository

```text
apps/api                 FastAPI API, worker, CLI, migrations, SQLite models
apps/web                 React desktop UI and typed API client
packages/contracts       Generated OpenAPI contract
tests/backend            Unit, property, failure, and integration tests
deploy/synology          Synology Container Manager example
docs                     Architecture and operations guides
```

## Local development

Requirements: Python 3.12+, Node.js 22+, and npm.

Start the API:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m file_curator --host 127.0.0.1 --port 8000
```

Start the UI in a second terminal:

```powershell
cd apps/web
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/health` to port 8000. Runtime data defaults to `apps/api/data`; set `FILE_CURATOR_CONFIG_DIR` to choose another location.

Useful checks:

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest --cov=file_curator
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src

cd ..\web
npm run typecheck
npm test -- --run
npm run build
```

## Container and Synology

Production is one non-root image containing the built UI, API, persistent job worker, migrations, and CLI. The image is published for amd64 and arm64 by GitHub Actions.

```sh
cp .env.example .env
docker compose up -d
```

Mount `/config` read-write for SQLite and backups. Mount allowed local directories below `/sources`; use read-only mounts for scan/preview and read-write mounts only when execution is required. Keep `FILE_CURATOR_WORKERS=1` because SQLite and the durable worker are coordinated in one process.

See [deployment](docs/deployment.md), [Synology](docs/synology.md), and [architecture](docs/architecture.md) for permissions, reverse proxy, backup, and upgrade guidance.

## Current implementation boundary

The v1 foundation includes local sources, metadata scans, processor revisions and traces, virtual plans, freeze/confirm, bounded execution, pause/cancel/retry, audit history, online SQLite backup, schedules, quarantine, and whole-batch rollback. The desktop UI is wired to the primary source, workflow, pipeline, review, plan, execution, backup, and rollback APIs.

Content hashing remains opt-in. Review items expose evidence but do not yet have per-item approval overrides; create a new workflow revision to change a decision. Docker image execution is validated in CI because a Docker engine is not required for local frontend/backend development.
