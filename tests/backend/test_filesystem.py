from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from file_curator.filesystem import (
    FileSafetyError,
    normalize_root,
    resolve_inside,
    resolved_path,
    safe_relative,
)


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
