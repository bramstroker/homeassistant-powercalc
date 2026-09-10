from io import BytesIO
import zipfile

from measure.profile.output import prepared_profile_archive


def test_prepared_profile_archive_is_reproducible_and_preserves_profile_paths() -> None:
    contents = (
        ("profile_library/acme/MODEL-1/model.json", b'{"name":"Desk lamp"}\n'),
        ("profile_library/acme/MODEL-1/brightness.csv.gz", b"compressed"),
    )

    first = prepared_profile_archive(contents)
    second = prepared_profile_archive(contents)

    assert first == second
    with zipfile.ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == [path for path, _content in contents]
        assert archive.read(contents[0][0]) == contents[0][1]
        assert archive.read(contents[1][0]) == contents[1][1]
