from io import BytesIO
import zipfile

from measure.profile.models import RenderedProfileFile
from measure.profile.output import prepared_profile_archive


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
