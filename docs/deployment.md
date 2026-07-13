# Deployment

The supported production artifact is a single multi-architecture container
image published at `ghcr.io/zaiwuli/file-curator`.

## Quick start

1. Create writable config and source directories.
2. Set their ownership to the UID/GID used by the container.
3. Copy `.env.example` to `.env` and edit the paths.
4. Start the service.

```sh
mkdir -p data/config data/sources
docker compose up -d
docker compose ps
```

Open `http://NAS_ADDRESS:8080`. Pin a version such as `1.0.0` for production;
do not rely on `latest` for controlled upgrades.

## Mount permissions

The container runs as `PUID:PGID`. Both values must be numeric and must have
access to `/config` and every source directory.

- Mount a source read-only (`:/sources/media:ro`) for scan and preview only.
- Mount it read-write when rename, move, quarantine, or rollback is required.
- Mount only the directories that File Curator is allowed to inspect.

The application must never be run as privileged and does not need the Docker
socket or host devices.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FILE_CURATOR_PORT` | `8080` | Host HTTP port |
| `FILE_CURATOR_BASE_PATH` | `/` | Reverse-proxy URL prefix |
| `FILE_CURATOR_LOG_LEVEL` | `INFO` | Application log level |
| `FILE_CURATOR_WEBHOOK_URL` | empty | Optional scan and execution summary webhook |
| `FILE_CURATOR_CONFIG_PATH` | `./data/config` | Host persistent data path |
| `FILE_CURATOR_SOURCES_PATH` | `./data/sources` | Host source root |
| `PUID` / `PGID` | `1000` | Runtime numeric user/group |
| `TZ` | `UTC` | Container timezone |

Do not increase `FILE_CURATOR_WORKERS`: SQLite writes and durable execution jobs
are intentionally coordinated by one application process.

Restore an online backup only while the service is stopped:

```sh
docker compose stop file-curator
docker compose run --rm file-curator python -m file_curator restore-backup --backup FILE.db
docker compose up -d
```

## Reverse proxy

For a dedicated host such as `curator.example.test`, leave the base path as `/`
and proxy all requests to port 8080. For a subpath such as `/file-curator`, set:

```env
FILE_CURATOR_BASE_PATH=/file-curator
```

The proxy must forward the original scheme and host. For a subpath deployment,
strip the external prefix uniformly before forwarding: external
`/file-curator/api/...` becomes internal `/api/...`, and
`/file-curator/assets/...` becomes `/assets/...`. Do not create separate rewrite
rules for API and SPA assets. Health checks remain available at `/health/live`
and `/health/ready` on the container port.

## Backup and restore

Use the application's backup command or UI before copying SQLite. A raw copy of
an active WAL database can be incomplete.

Minimum backup set:

```text
/config/file-curator.db backup
/config/exports
deployment .env and compose.yaml
```

Source files are not application backups and are never copied into `/config`.
To restore, stop the container, restore a matched database backup into an empty
config directory, preserve ownership, and start the pinned image version.

## Upgrade and rollback

1. Export workflows and create an online database backup.
2. Pin the new image version in `.env`.
3. Pull and recreate the container.
4. Wait for `/health/ready` and inspect the migration status.
5. Run a read-only sample scan before enabling scheduled work.

```sh
docker compose pull
docker compose up -d
docker compose logs --tail=100 file-curator
```

If migration or startup fails, stop the service, restore the pre-upgrade
database backup, pin the previous image, and recreate the container. Do not run
an older image against a database already migrated by a newer version.
