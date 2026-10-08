from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
import zipfile

from measure.profile.models import ProfileMetadata, ProfilePreview, RenderedProfileFile
from measure.profile.output import prepared_profile_archive, write_prepared_profile
from measure.profile.prepare import ProfilePreparationError, ProfilePreparer
import pytest


def test_prepared_profile_archive_is_reproducible_and_preserves_profile_paths() -> None:
    contents = [
        RenderedProfileFile(path="profile_library/acme/MODEL-1/model.json", content=b'{"name":"Desk lamp"}\n'),
        RenderedProfileFile(path="profile_library/acme/MODEL-1/brightness.csv.gz", content=b"compressed"),
    ]

    first = prepared_profile_archive(contents)
    second = prepared_profile_archive(contents)

    assert first == second
    with zipfile.ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == [file.path for file in contents]
        for file in contents:
            assert archive.read(file.path) == file.content


@pytest.mark.parametrize("escape_path", ["../outside.json", "profile_library/../../outside.json"])
def test_write_prepared_profile_rejects_escaping_paths_before_writing_any_files(
    tmp_path: Path,
    escape_path: str,
) -> None:
    preparer = MagicMock(spec=ProfilePreparer)
    preparer.prepare.return_value = ProfilePreview(manufacturer_directory="acme", model_directory="MODEL-1", files=())
    preparer.render_contents.return_value = [
        RenderedProfileFile("profile_library/acme/MODEL-1/model.json", b"{}"),
        RenderedProfileFile(escape_path, b"unsafe"),
    ]
    output = tmp_path / "output"

    with pytest.raises(ProfilePreparationError, match="escapes the output directory"):
        write_prepared_profile(
            preparer=preparer,
            artifact_directory=tmp_path / "artifacts",
            metadata=ProfileMetadata(manufacturer="Acme", model_id="MODEL-1"),
            output_directory=output,
        )

    assert not output.exists()
    assert not (tmp_path / "outside.json").exists()
