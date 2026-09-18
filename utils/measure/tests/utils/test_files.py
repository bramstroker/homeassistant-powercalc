from pathlib import Path
import tempfile
from unittest.mock import patch

from measure.utils.files import write_bytes_atomic
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
