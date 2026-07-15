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

## Version 1.0 capabilities

Version 1.0 includes local sources, metadata and opt-in hash scans, file browsing, file groups, deterministic processor revisions and traces, per-file review decisions, virtual plans, freeze/confirm, preflight, bounded execution, post-operation verification, pause/cancel/retry, audit history, online SQLite backup, scheduled scans, webhook summaries, quarantine, rollback simulation, and whole-batch rollback.

Workflow Engine 2.0 adds eight ordered processing gates, visual condition and action cards, built-in templates, YAML/JSON import and export, legacy v1 conversion, multi-date extraction, protected number cleanup, parent-folder inheritance, same-source archive and move actions, quarantine review, conflict policies, single-rule testing, and impact summaries. Raw JSON is kept in an optional developer section; common rules can be configured through forms.

Workflow Builder 3.0 centralizes scan readiness, full scope filters, processor-generated option forms, associated-file policies, impact thresholds, revision comparison and restoration, and three duplicate matching methods (`name_size`, `normalized_name_size`, and opt-in content `hash`). Scheduled scans may generate a draft preview plan for a selected workflow; they never freeze, confirm, or execute that plan.

The v2.1 junk-rule foundation adds a versioned BT advertisement and junk rule pack, metadata-only keyword/regex/extension/path/size checks, protected sidecar extensions, explainable evidence and scores, custom processor options, rule-pack validation APIs, and a desktop rule-library page. Matches remain review or quarantine candidates; permanent deletion is still unsupported.

The desktop UI supports English and Simplified Chinese and is wired to source, browser, workflow, review, plan, execution, recovery, scheduling, backup, and diagnostics APIs. Content hashing remains explicitly opt-in. Restore a backup while the service is stopped with `python -m file_curator restore-backup --backup FILE.db`.

Set `FILE_CURATOR_WEBHOOK_URL` to receive scan and execution completion summaries. The payload contains job identifiers, status, and counters; it does not include file paths. Docker image execution is validated in CI because a Docker engine is not required for local frontend/backend development.

Run the desktop end-to-end suite with `npm run test:e2e` after installing Chromium using `npx playwright install chromium`.

See [Workflow Engine 2.0](docs/workflow-v2.md) for template authoring, AI-assisted template paste, safety limits, and a complete example.
