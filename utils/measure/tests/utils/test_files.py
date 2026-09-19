from datetime import UTC, datetime
from enum import StrEnum
import json
from pathlib import Path
import stat
import tempfile
from unittest.mock import patch

from measure.utils.files import write_bytes_atomic, write_json_atomic
import pytest


@pytest.mark.parametrize("existing", [False, True])
def test_write_bytes_atomic_preserves_content_and_leaves_no_temporary_file(tmp_path: Path, existing: bool) -> None:
    path = tmp_path / "profile.zip"
    if existing:
        path.write_bytes(b"old")

    write_bytes_atomic(path, b"new\x00\xff")

    assert path.read_bytes() == b"new\x00\xff"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_failed_binary_replacement_preserves_original_and_cleans_up(
    tmp_path: Path, error_type: type[BaseException]
) -> None:
    path = tmp_path / "profile.zip"
    path.write_bytes(b"original")

    with patch.object(Path, "replace", side_effect=error_type("Interrupted")), pytest.raises(error_type):
        write_bytes_atomic(path, b"replacement")

    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_failed_binary_write_preserves_original_and_cleans_up(tmp_path: Path, error_type: type[BaseException]) -> None:
    path = tmp_path / "profile.zip"
    path.write_bytes(b"original")
    with (
        tempfile.NamedTemporaryFile(dir=tmp_path, delete=False) as file,
        patch("measure.utils.files.tempfile.NamedTemporaryFile", return_value=file),
        patch.object(file, "write", side_effect=error_type("Interrupted")),
        pytest.raises(error_type),
    ):
        write_bytes_atomic(path, b"replacement")

    assert file.closed
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_temporary_file_creation_preserves_original(tmp_path: Path) -> None:
    path = tmp_path / "profile.zip"
    path.write_bytes(b"original")

    with (
        patch("measure.utils.files.tempfile.NamedTemporaryFile", side_effect=OSError("No space")),
        pytest.raises(OSError, match="No space"),
    ):
        write_bytes_atomic(path, b"replacement")

    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("private", [False, True])
def test_atomic_json_write_creates_parents_and_serializes_domain_values(tmp_path: Path, private: bool) -> None:
    class State(StrEnum):
        COMPLETED = "completed"

    path = tmp_path / "session" / "state.json"
    timestamp = datetime(2026, 9, 18, tzinfo=UTC)

    write_json_atomic(path, {"state": State.COMPLETED, "created_at": timestamp}, private=private)

    assert json.loads(path.read_text()) == {"state": "completed", "created_at": str(timestamp)}
    assert list(path.parent.iterdir()) == [path]
    if private:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("failure_point", ["json.dump", "os.fsync", "replace"])
@pytest.mark.parametrize("private", [False, True])
def test_atomic_json_failure_preserves_original_and_removes_temporary_file(
    tmp_path: Path,
    failure_point: str,
    private: bool,
) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"state": "running"}', encoding="utf-8")
    failure = OSError("Disk unavailable")
    target = (
        patch.object(Path, "replace", side_effect=failure)
        if failure_point == "replace"
        else patch(
            f"measure.utils.files.{failure_point}",
            side_effect=failure,
        )
    )

    with target, pytest.raises(OSError, match="Disk unavailable") as error:
        write_json_atomic(path, {"state": "completed"}, private=private)

    assert error.value is failure
    assert json.loads(path.read_text()) == {"state": "running"}
    assert list(tmp_path.iterdir()) == [path]
