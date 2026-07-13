# Synology DSM

File Curator supports DSM 7.2+ with Container Manager on x86-64 and ARM64 NAS
models that support Docker.

## Prepare directories

Create an application directory and identify the numeric UID/GID that owns the
media files. Example layout:

```text
/volume1/docker/file-curator/config
/volume1/media
```

Copy `deploy/synology/compose.yaml` and its `.env.example` into a Container
Manager project directory. Create `.env`, then set:

```env
CONFIG_PATH=/volume1/docker/file-curator/config
SOURCES_PATH=/volume1/media
PUID=1026
PGID=100
```

The sample IDs are placeholders. Use the actual numeric account and group IDs
from DSM. Grant that identity read/write access to the config directory. Grant
only the source permissions needed for the selected File Curator operation.

## Create the project

In Container Manager, create a Project from the Compose file, select the folder
containing `.env`, and build the project. The first startup may take longer while
DSM downloads the architecture-specific image.

Check the health status before opening `http://NAS_ADDRESS:8080`.

## DSM reverse proxy

DSM Control Panel can expose the service over HTTPS:

1. Create a reverse proxy rule from an HTTPS hostname to `127.0.0.1:8080`.
2. Forward `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and
   `X-Forwarded-For` headers.
3. Use `FILE_CURATOR_BASE_PATH=/` for a dedicated hostname.
4. Restrict access through DSM firewall or a trusted LAN/VPN.

When publishing below a subpath, set `FILE_CURATOR_BASE_PATH` and configure DSM
to strip that same prefix before forwarding requests to the container.

## Operational notes

- Keep `/config` on a local Synology volume, never inside a remote mount.
- A disconnected source should make that source unavailable, not restart the
  application container.
- Start with read-only source mounts while validating workflows.
- Use low scan/execution concurrency for slow or remotely backed directories.
- Snapshot `/config` only after an application backup has completed.
- Configure `FILE_CURATOR_WEBHOOK_URL` only for a trusted HTTPS endpoint; payloads contain job summaries but no file paths.
