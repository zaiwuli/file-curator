from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from file_curator.filesystem import (
    FileSafetyError,
    iter_metadata,
    normalize_root,
    resolve_inside,
    resolved_path,
    safe_relative,
)


def test_metadata_scan_skips_transient_entry_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good_path = tmp_path / "good.mp4"
    missing_path = tmp_path / "missing.mp4"

    class Entry:
        def __init__(self, path: Path, *, missing: bool = False) -> None:
            self.path = str(path)
            self.name = path.name
            self.missing = missing

        def stat(self, *, follow_symlinks: bool = False):
            assert follow_symlinks is False
            if self.missing:
                raise FileNotFoundError(self.path)
            return type("Stat", (), {"st_size": 42, "st_mtime_ns": 123})()

        def is_dir(self, *, follow_symlinks: bool = False) -> bool:
            assert follow_symlinks is False
            return False

        def is_symlink(self) -> bool:
            return False

    class ScanContext:
        class Entries:
            def __init__(self) -> None:
                self.items = iter([Entry(missing_path, missing=True), Entry(good_path)])
                self.failed = False

            def __iter__(self):
                return self

            def __next__(self):
                if not self.failed:
                    self.failed = True
                    raise FileNotFoundError(tmp_path)
                return next(self.items)

        def __enter__(self):
            return self.Entries()

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr("file_curator.filesystem.os.scandir", lambda _: ScanContext())
    errors: list[tuple[Path, str]] = []

    result = list(
        iter_metadata(
            tmp_path,
            exclusions=[],
            max_entries=10,
            on_error=lambda path, exc: errors.append((path, type(exc).__name__)),
        )
    )

    assert [item["relative_path"] for item in result] == ["good.mp4"]
    assert errors == [
        (Path("."), "FileNotFoundError"),
        (Path("missing.mp4"), "FileNotFoundError"),
    ]


@given(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=64,
    )
)
def test_plain_filename_stays_inside(value: str) -> None:
    root = Path.cwd().resolve()
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
    if value.rstrip(" .").split(".", 1)[0].upper() in reserved:
        with pytest.raises(FileSafetyError, match="path.outside_source"):
            resolve_inside(root, value)
    else:
        candidate = resolve_inside(root, value)
        assert candidate == root / value


@pytest.mark.parametrize("value", ["../secret", "/etc/passwd", "C:\\Windows", "a/../../b", "COM1", "NUL.txt"])
def test_unsafe_relative_paths_are_rejected(value: str) -> None:
    with pytest.raises(FileSafetyError, match="path.outside_source"):
        safe_relative(value)


def test_windows_mount_falls_back_when_realpath_reports_unrecognized_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_resolve = Path.resolve

    def fail_resolve(path: Path, strict: bool = False) -> Path:
        error = OSError("unrecognized filesystem")
        error.winerror = 1005  # type: ignore[attr-defined]
        raise error

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    assert resolved_path(tmp_path, strict=True) == Path(str(tmp_path.absolute()))
    assert normalize_root(tmp_path) == Path(str(tmp_path.absolute()))
    monkeypatch.setattr(Path, "resolve", original_resolve)
