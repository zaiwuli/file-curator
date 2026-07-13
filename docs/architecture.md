# Architecture

File Curator is a local-first application. It indexes file metadata, evaluates a
deterministic workflow, and stores proposed paths in SQLite. The filesystem is
not changed until a user freezes and confirms a plan.

## Runtime topology

Development uses two processes:

- `apps/api`: FastAPI on port 8000.
- `apps/web`: Vite on port 5173, proxying `/api` to FastAPI.

Production uses one container and one Python application process. The image
contains the backend wheel, migrations, worker, CLI, and the compiled React
assets. FastAPI serves `/api/*`, `/health/*`, and the SPA fallback.

```text
Browser
  |-- /api/* ------ FastAPI routes
  |-- /health/* --- health routes
  `-- /* ---------- compiled React application
                         |
                    SQLite /config
                         |
                    sources /sources
```

## Build contract

- The frontend lives in `apps/web`, is installed with `npm ci`, and writes its
  production build to `apps/web/dist`.
- The backend lives in `apps/api`, builds as a wheel, and starts with
  `python -m file_curator`.
- `FILE_CURATOR_UI_DIR=/app/static` identifies the bundled frontend.
- `FILE_CURATOR_BASE_PATH` configures reverse-proxy subpath deployments.
- `/health/live` tests the process. `/health/ready` tests application readiness.

## Persistent data

Only `/config` contains application state. It holds SQLite, backups, exports,
and logs. `/sources` contains bind-mounted user files and must never contain the
application database. SQLite must be stored on a local Btrfs/ext4 volume, not a
FUSE, SMB, NFS, or other remote mount.

All source paths stored in the database are source identifiers plus relative
paths. Host paths are deployment configuration and are not embedded into plans.

## Security boundaries

- The image has a non-root user and the Compose service drops all capabilities.
- The root filesystem is read-only; only `/config`, `/sources`, and `/tmp` are
  writable according to mount permissions.
- The backend is the only component with source filesystem access.
- A frozen plan records source metadata and is validated again before execution.
- The executor does not support permanent deletion or cross-source copies.

## Versioning

The application, processor manifests, and workflow templates are versioned
independently. Frozen plans retain all three versions so historical decisions
remain explainable after an upgrade.

