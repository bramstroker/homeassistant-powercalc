from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from measure.contribution.models import ContributionAuthor, ContributionMetadata
from measure.contribution.prepare import ProfilePreparationError, ProfilePreparer
import pytest


def metadata(
    manufacturer: str = "Philips",
    model_id: str = "LCT999",
    product_name: str | None = None,
) -> ContributionMetadata:
    return ContributionMetadata(
        manufacturer=manufacturer,
        model_id=model_id,
        product_name=product_name,
        author=ContributionAuthor(name="Test User", github="test-user", email="test@example.com"),
    )


def write_profile_artifacts(path: Path, *, name: str = "New lamp") -> None:
    path.mkdir()
    (path / "model.json").write_text(
        json.dumps(
            {
                "name": name,
                "device_type": "light",
                "measure_method": "script",
                "measure_device": "Test meter",
                "calculation_strategy": "lut",
                "created_at": "2026-07-24T10:00:00Z",
                "standby_power": 0.4,
            },
        ),
        encoding="utf-8",
    )
    with gzip.open(path / "brightness.csv.gz", "wt", encoding="utf-8") as file:
        file.write("bri,watt\n1,1.0\n")


def write_library(path: Path) -> None:
    (path / "signify" / "LCT010").mkdir(parents=True)
    (path / "signify" / "manufacturer.json").write_text(
        json.dumps({"name": "Signify", "aliases": ["Philips"]}),
        encoding="utf-8",
    )
    (path / "signify" / "LCT010" / "model.json").write_text(
        json.dumps({"name": "Existing lamp", "aliases": ["Old lamp"]}),
        encoding="utf-8",
    )


def test_preparer_canonicalizes_manufacturer_enriches_author_and_keeps_aliases_unchanged(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    write_library(library)
    schema.write_text("{}", encoding="utf-8")
    write_profile_artifacts(artifacts)
    seen_model: dict[str, Any] = {}

    def validator(instance: dict[str, Any], _: dict[str, Any]) -> None:
        seen_model.update(instance)

    preparer = ProfilePreparer(library_root=library, model_schema_path=schema, validator=validator)
    contribution_metadata = metadata(product_name="Hue test lamp")
    preview = preparer.prepare(artifacts, contribution_metadata)

    assert preview.manufacturer_directory == "signify"
    assert [file.path for file in preview.files] == [
        "profile_library/signify/LCT999/model.json",
        "profile_library/signify/LCT999/brightness.csv.gz",
    ]
    assert seen_model["author_info"] == {"name": "Test User", "github": "test-user", "email": "test@example.com"}
    assert seen_model["name"] == "Hue test lamp"
    assert "aliases" not in seen_model
    prepared_contents = dict(preparer.prepared_contents(artifacts, contribution_metadata, preview))
    prepared_model = json.loads(prepared_contents[preview.files[0].path])
    assert prepared_model["name"] == "Hue test lamp"
    assert "aliases" not in prepared_model
    assert all(file.sha for file in preview.files)


def test_preparer_generates_new_manufacturer_manifest_without_adding_aliases(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    schema.write_text("{}", encoding="utf-8")
    write_profile_artifacts(artifacts)

    preparer = ProfilePreparer(
        library_root=library,
        model_schema_path=schema,
        validator=lambda _instance, _schema: None,
    )

    preview = preparer.prepare(artifacts, metadata("Acme"))

    assert "profile_library/acme/manufacturer.json" in {file.path for file in preview.files}
    contents = dict(preparer.prepared_contents(artifacts, metadata("Acme"), preview))
    assert json.loads(contents["profile_library/acme/manufacturer.json"]) == {"name": "Acme", "aliases": []}


def test_preparer_allows_generated_linear_profile_without_csv(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    write_library(library)
    schema.write_text("{}", encoding="utf-8")
    artifacts.mkdir()
    (artifacts / "model.json").write_text(
        json.dumps({"name": "Speaker", "calculation_strategy": "linear"}),
        encoding="utf-8",
    )

    preview = ProfilePreparer(
        library_root=library,
        model_schema_path=schema,
        validator=lambda _instance, _schema: None,
    ).prepare(artifacts, metadata(model_id="Speaker 1"))

    assert [file.path for file in preview.files] == ["profile_library/signify/Speaker 1/model.json"]


def test_preparer_blocks_collisions_and_warns_on_duplicates(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    write_library(library)
    schema.write_text("{}", encoding="utf-8")
    write_profile_artifacts(artifacts, name="Old lamp")

    preparer = ProfilePreparer(
        library_root=library,
        model_schema_path=schema,
        validator=lambda _instance, _schema: None,
    )
    preview = preparer.prepare(artifacts, metadata())

    assert preview.warnings == ("Possible duplicate profile: profile_library/signify/LCT010/model.json",)

    with pytest.raises(ProfilePreparationError, match="Refusing to overwrite"):
        preparer.prepare(artifacts, metadata(model_id="LCT010"))


def test_preparer_uses_downloaded_library_index_for_aliases_and_collisions(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    schema.write_text("{}", encoding="utf-8")
    (library / "library.json").write_text(
        json.dumps(
            {
                "manufacturers": [
                    {
                        "name": "signify",
                        "full_name": "Signify",
                        "aliases": ["Philips"],
                        "dir_name": "signify",
                        "models": [{"id": "LCT010", "name": "Existing lamp", "aliases": ["Old lamp"]}],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    write_profile_artifacts(artifacts)
    preparer = ProfilePreparer(
        library_root=library,
        model_schema_path=schema,
        validator=lambda _instance, _schema: None,
    )

    preview = preparer.prepare(artifacts, metadata(model_id="LCT999"))

    assert preview.manufacturer_directory == "signify"
    with pytest.raises(ProfilePreparationError, match="Refusing to overwrite"):
        preparer.prepare(artifacts, metadata(model_id="LCT010"))


def test_preparer_accepts_raw_csv_alongside_gzip_and_rejects_unrelated_artifacts(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    write_library(library)
    schema.write_text("{}", encoding="utf-8")
    write_profile_artifacts(artifacts)
    (artifacts / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")

    preparer = ProfilePreparer(
        library_root=library,
        model_schema_path=schema,
        validator=lambda _instance, _schema: None,
    )
    preview = preparer.prepare(artifacts, metadata())

    assert [file.path for file in preview.files].count("profile_library/signify/LCT999/brightness.csv.gz") == 1
    assert "profile_library/signify/LCT999/brightness.csv" not in {file.path for file in preview.files}

    (artifacts / "debug.txt").write_text("not a profile artifact", encoding="utf-8")
    with pytest.raises(ProfilePreparationError, match="Unexpected artifact"):
        preparer.prepare(artifacts, metadata())


def test_preparer_compresses_raw_csv_for_profile_library(tmp_path: Path) -> None:
    library = tmp_path / "profile_library"
    schema = tmp_path / "model_schema.json"
    artifacts = tmp_path / "artifacts"
    library.mkdir()
    write_library(library)
    schema.write_text("{}", encoding="utf-8")
    write_profile_artifacts(artifacts)
    (artifacts / "brightness.csv.gz").unlink()
    raw_content = b"bri,watt\n1,1.0\n"
    (artifacts / "brightness.csv").write_bytes(raw_content)
    preparer = ProfilePreparer(
        library_root=library,
        model_schema_path=schema,
        validator=lambda _instance, _schema: None,
    )

    preview = preparer.prepare(artifacts, metadata())
    contents = dict(preparer.prepared_contents(artifacts, metadata(), preview))

    assert gzip.decompress(contents["profile_library/signify/LCT999/brightness.csv.gz"]) == raw_content
