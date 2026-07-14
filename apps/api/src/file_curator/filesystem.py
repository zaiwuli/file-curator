import hashlib
import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .db import FileEntry, ScanJob, Source, utcnow


class FileSafetyError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalize_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise FileSafetyError("source.not_directory")
    return root


def safe_relative(value: str) -> Path:
    path = Path(value)
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
    if (
        path.is_absolute()
        or path.anchor
        or path.drive
        or ":" in value
        or any(part == ".." for part in path.parts)
        or any(part.rstrip(" .").split(".", 1)[0].upper() in reserved for part in path.parts)
    ):
        raise FileSafetyError("path.outside_source")
    return path


def resolve_inside(root: Path, relative: str, *, strict: bool = False) -> Path:
    candidate = (root / safe_relative(relative)).resolve(strict=strict)
    try:
        candidate.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise FileSafetyError("path.outside_source") from exc
    return candidate


def probe_capabilities(root: Path, read_only: bool = False) -> dict[str, Any]:
    exists = root.exists()
    readable = exists and os.access(root, os.R_OK)
    writable = exists and not read_only and os.access(root, os.W_OK)
    return {
        "online": exists,
        "read": readable,
        "list": readable and root.is_dir(),
        "write": writable,
        "create": writable,
        "rename": writable,
        "move": writable,
        "quarantine": writable,
    }


def is_excluded(relative: Path, patterns: list[str]) -> bool:
    normalized = relative.as_posix()
    return any(
        relative.match(pattern) or normalized.startswith(pattern.rstrip("/") + "/")
        for pattern in patterns
    )


def iter_metadata(root: Path, exclusions: list[str], max_entries: int) -> Iterator[dict[str, Any]]:
    pending = [root]
    emitted = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            for item in iterator:
                relative = Path(item.path).relative_to(root)
                if is_excluded(relative, exclusions):
                    continue
                stat = item.stat(follow_symlinks=False)
                is_dir = item.is_dir(follow_symlinks=False)
                yield {
                    "relative_path": relative.as_posix(),
                    "parent_path": relative.parent.as_posix()
                    if relative.parent != Path(".")
                    else "",
                    "name": item.name,
                    "extension": Path(item.name).suffix.lower() if not is_dir else "",
                    "size": stat.st_size if not is_dir else 0,
                    "mtime_ns": stat.st_mtime_ns,
                    "is_dir": is_dir,
                }
                emitted += 1
                if emitted > max_entries:
                    raise FileSafetyError("scan.entry_limit_exceeded")
                if is_dir and not item.is_symlink():
                    pending.append(Path(item.path))


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


TEXT_INSPECTION_EXTENSIONS = {".txt", ".url", ".website", ".html", ".htm"}
TEXT_INSPECTION_LIMIT = 128 * 1024
TEXT_SIGNAL_PATTERNS = {
    "url": re.compile(r"(?i)https?://|www\."),
    "promotion": re.compile(r"(?i)广告|推广|更多资源|最新网址|扫码|关注|promo|download more"),
    "contact": re.compile(r"(?i)(?:qq|telegram|wechat|vx|群)[\s:：_-]*[a-z0-9_-]{4,}"),
}


def inspect_small_text(path: Path, size: int) -> list[str]:
    if path.suffix.casefold() not in TEXT_INSPECTION_EXTENSIONS or size > TEXT_INSPECTION_LIMIT:
        return []
    data = path.read_bytes()[:TEXT_INSPECTION_LIMIT]
    text = data.decode("utf-8", errors="ignore")
    if not text:
        text = data.decode("gb18030", errors="ignore")
    return [name for name, pattern in TEXT_SIGNAL_PATTERNS.items() if pattern.search(text)]


def scan_source(
    session: Any,
    source: Source,
    job: ScanJob,
    max_entries: int,
    control: Callable[[], str] | None = None,
) -> ScanJob:
    root = normalize_root(source.root_path)
    job.status = "running"
    session.commit()
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    try:
        for data in iter_metadata(root, source.exclusions, max_entries):
            requested = control() if control else "running"
            if requested in {"pause_requested", "cancel_requested"}:
                job.status = "paused" if requested == "pause_requested" else "cancelled"
                session.commit()
                return job
            seen.add(data["relative_path"])
            existing = (
                session.query(FileEntry)
                .filter_by(source_id=source.id, relative_path=data["relative_path"], active=True)
                .one_or_none()
            )
            if existing:
                content_changed = (
                    existing.size != data["size"] or existing.mtime_ns != data["mtime_ns"]
                )
                if job.hash_contents and not data["is_dir"]:
                    data["content_hash"] = hash_file(root / data["relative_path"])
                elif content_changed:
                    existing.content_hash = None
                if job.inspect_small_text and not data["is_dir"]:
                    data["text_signals"] = inspect_small_text(
                        root / data["relative_path"], data["size"]
                    )
                elif content_changed:
                    existing.text_signals = []
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.scan_job_id = job.id
            else:
                if job.hash_contents and not data["is_dir"]:
                    data["content_hash"] = hash_file(root / data["relative_path"])
                if job.inspect_small_text and not data["is_dir"]:
                    data["text_signals"] = inspect_small_text(
                        root / data["relative_path"], data["size"]
                    )
                session.add(FileEntry(source_id=source.id, scan_job_id=job.id, **data))
            job.scanned_count += 1
            job.cursor = data["relative_path"]
            if job.scanned_count % 500 == 0:
                session.commit()
        stale = session.query(FileEntry).filter_by(source_id=source.id, active=True).all()
        for entry in stale:
            if entry.relative_path not in seen:
                entry.active = False
        job.status = "completed"
        job.completed_at = utcnow()
    except (OSError, FileSafetyError) as exc:
        errors.append({"path": job.cursor or "", "error": getattr(exc, "code", type(exc).__name__)})
        job.status = "partial" if job.scanned_count else "failed"
        job.error_count = len(errors)
        job.errors = errors
    session.commit()
    return job
