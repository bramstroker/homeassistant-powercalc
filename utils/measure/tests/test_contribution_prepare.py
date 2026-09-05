import gzip
import json
from pathlib import Path
from typing import Any

from measure.contribution.models import ContributionAuthor, ContributionMetadata
from measure.contribution.prepare import JsonValidator, ProfilePreparationError, ProfilePreparer
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
        mains_voltage=230,
        author=ContributionAuthor(name="Test User", github="test-user", email="test@example.com"),
    )


# The one manufacturer/model the library fixtures describe, whether they write it as
# an on-disk profile tree (write_library) or as a downloaded index (write_library_index).
EXISTING_DIRECTORY = "signify"
EXISTING_MANUFACTURER = "Signify"
EXISTING_ALIAS = "Philips"
EXISTING_MODEL_ID = "LCT010"
EXISTING_MODEL_NAME = "Existing lamp"
EXISTING_MODEL_ALIAS = "Old lamp"


def library_root(tmp_path: Path) -> Path:
    """The profile library directory every fixture and preparer in this module shares."""
    library = tmp_path / "profile_library"
    library.mkdir(parents=True, exist_ok=True)
    return library


def make_preparer(tmp_path: Path, validator: JsonValidator | None = None) -> ProfilePreparer:
    """Preparer over ``library_root(tmp_path)`` with a permissive schema and no-op validator."""
    schema = tmp_path / "model_schema.json"
    schema.write_text("{}", encoding="utf-8")
    return ProfilePreparer(
        library_root=library_root(tmp_path),
        model_schema_path=schema,
        validator=validator or (lambda _instance, _schema: None),
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


def write_library(tmp_path: Path) -> None:
    """Seed the existing profile as an on-disk library checkout."""
    library = library_root(tmp_path)
    profile = library / EXISTING_DIRECTORY / EXISTING_MODEL_ID
    profile.mkdir(parents=True)
    (library / EXISTING_DIRECTORY / "manufacturer.json").write_text(
        json.dumps({"name": EXISTING_MANUFACTURER, "aliases": [EXISTING_ALIAS]}),
        encoding="utf-8",
    )
    (profile / "model.json").write_text(
        json.dumps({"name": EXISTING_MODEL_NAME, "aliases": [EXISTING_MODEL_ALIAS]}),
        encoding="utf-8",
    )


def write_library_index(tmp_path: Path, *, full_name: bool = False, model_aliases: bool = False) -> None:
    """Seed the same existing profile as a downloaded ``library.json`` index."""
    model: dict[str, Any] = {"id": EXISTING_MODEL_ID, "name": EXISTING_MODEL_NAME}
    if model_aliases:
        model["aliases"] = [EXISTING_MODEL_ALIAS]
    manufacturer: dict[str, Any] = {
        "name": EXISTING_DIRECTORY,
        "aliases": [EXISTING_ALIAS],
        "dir_name": EXISTING_DIRECTORY,
        "models": [model],
    }
    if full_name:
        manufacturer["full_name"] = EXISTING_MANUFACTURER
    index = library_root(tmp_path) / "library.json"
    index.write_text(json.dumps({"manufacturers": [manufacturer]}), encoding="utf-8")


def test_preparer_canonicalizes_manufacturer_enriches_author_and_keeps_aliases_unchanged(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)
    seen_model: dict[str, Any] = {}

    def validator(instance: dict[str, Any], _: dict[str, Any]) -> None:
        seen_model.update(instance)

    preparer = make_preparer(tmp_path, validator)
    contribution_metadata = metadata(product_name="Hue test lamp")
    preview = preparer.prepare(artifacts, contribution_metadata)

    assert preview.manufacturer_directory == "signify"
    assert [file.path for file in preview.files] == [
        "profile_library/signify/LCT999/model.json",
        "profile_library/signify/LCT999/brightness.csv.gz",
    ]
    assert seen_model["authors"] == [{"name": "Test User", "github": "test-user", "email": "test@example.com"}]
    assert seen_model["name"] == "Hue test lamp"
    assert "aliases" not in seen_model
    prepared_contents = dict(preparer.render_contents(artifacts, contribution_metadata, preview))
    prepared_model = json.loads(prepared_contents[preview.files[0].path])
    assert prepared_model["name"] == "Hue test lamp"
    assert "aliases" not in prepared_model
    assert all(file.sha for file in preview.files)


def test_preparer_applies_delivery_independent_profile_metadata(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)
    preparer = make_preparer(tmp_path)
    contribution_metadata = ContributionMetadata(
        manufacturer="Philips",
        model_id="LCT999",
        product_name="Hue test lamp",
        aliases=("Hue test",),
        gtins=("12345678", "1234567890123"),
        product_url="https://example.com/hue-test",
        mains_voltage=230,
        device_specs={"rated_power": 9.5},
        measure_device="Shelly PM Mini Gen3",
        measure_device_firmware="1.7.0",
        measure_description="Measured at 230 V",
        author=ContributionAuthor(name="Test User", github="test-user"),
    )

    preview = preparer.prepare(artifacts, contribution_metadata)
    model = json.loads(dict(preparer.render_contents(artifacts, contribution_metadata, preview))[preview.files[0].path])

    assert model["aliases"] == ["Hue test"]
    assert model["ean"] == ["12345678", "1234567890123"]
    assert model["product_url"] == "https://example.com/hue-test"
    assert model["device_specs"] == {"rated_power": 9.5}
    assert model["measure_device"] == "Shelly PM Mini Gen3"
    assert model["measure_device_firmware"] == "1.7.0"
    assert model["measure_description"] == "Measured at 230 V"


def test_preparer_derives_mains_voltage_from_measured_voltage_range(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_profile_artifacts(artifacts)
    artifact_model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    artifact_model["voltage_range"] = {"min": 117.2, "max": 122.1}
    (artifacts / "model.json").write_text(json.dumps(artifact_model), encoding="utf-8")

    voltage_metadata = metadata().model_copy(update={"mains_voltage": None})
    preparer = make_preparer(tmp_path)
    preview = preparer.prepare(artifacts, voltage_metadata)
    model = json.loads(dict(preparer.render_contents(artifacts, voltage_metadata, preview))[preview.files[0].path])

    assert model["mains_voltage"] == 120


def test_preparer_requires_mains_voltage_when_no_voltage_range_was_measured(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_profile_artifacts(artifacts)
    preparer = make_preparer(tmp_path)
    profile_metadata = metadata().model_copy(update={"mains_voltage": None})

    with pytest.raises(ProfilePreparationError, match="Select the nominal mains voltage") as error:
        preparer.prepare(artifacts, profile_metadata)

    assert error.value.field == "mains_voltage"


def test_preparer_omits_empty_optional_profile_metadata(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)
    artifact_model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    artifact_model.update(
        {
            "aliases": [],
            "ean": [],
            "product_url": "",
            "device_specs": {},
            "measure_device_firmware": " ",
            "measure_description": "",
        },
    )
    (artifacts / "model.json").write_text(json.dumps(artifact_model), encoding="utf-8")
    contribution_metadata = metadata()
    contribution_metadata = contribution_metadata.model_copy(update={"aliases": (), "gtins": (), "device_specs": {}})

    preview = make_preparer(tmp_path).prepare(artifacts, contribution_metadata)
    model = json.loads(
        dict(make_preparer(tmp_path).render_contents(artifacts, contribution_metadata, preview))[preview.files[0].path],
    )

    assert not {
        "aliases",
        "ean",
        "product_url",
        "device_specs",
        "measure_device_firmware",
        "measure_description",
    }.intersection(model)


def test_preparer_reports_model_schema_validation_errors(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)
    schema = tmp_path / "model_schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"device_type": {"enum": ["fan"]}},
            },
        ),
        encoding="utf-8",
    )
    preparer = ProfilePreparer(library_root=library_root(tmp_path), model_schema_path=schema)
    profile_metadata = metadata()

    with pytest.raises(
        ProfilePreparationError,
        match=r"model\.json does not match model_schema\.json at device_type: 'light' is not one of",
    ):
        preparer.prepare(artifacts, profile_metadata)


@pytest.mark.parametrize("field", ["product_url", "measure_device_firmware", "measure_description"])
def test_preparer_clears_explicitly_blank_optional_text_but_preserves_omitted_fields(field: str) -> None:
    from measure.profile.models import ProfileMetadata

    model = {field: "https://example.com" if field == "product_url" else "Original value"}
    omitted = ProfileMetadata(manufacturer="Acme", model_id="Test")
    assert ProfilePreparer._apply_metadata(dict(model), omitted) == model  # noqa: SLF001
    cleared = ProfileMetadata.model_validate({"manufacturer": "Acme", "model_id": "Test", field: "  "})
    assert field not in ProfilePreparer._apply_metadata(dict(model), cleared)  # noqa: SLF001


@pytest.mark.parametrize(
    "instance,schema,field",
    [
        ({"name": 123}, {"properties": {"name": {"type": "string"}}}, "product_name"),
        ({"ean": [123]}, {"properties": {"ean": {"items": {"type": "string"}}}}, "gtins"),
        (
            {"device_specs": {"rated_power": -1}},
            {"properties": {"device_specs": {"properties": {"rated_power": {"minimum": 0}}}}},
            "device_specs.rated_power",
        ),
        (
            {"authors": [{"email": 123}]},
            {"properties": {"authors": {"items": {"properties": {"email": {"type": "string"}}}}}},
            "contributor_email",
        ),
    ],
)
def test_schema_errors_identify_editable_fields(instance: dict, schema: dict, field: str) -> None:
    from measure.contribution.prepare import _jsonschema_validate

    with pytest.raises(ProfilePreparationError) as info:
        _jsonschema_validate(instance, schema)
    assert info.value.field == field


def test_preparer_generates_new_manufacturer_manifest_without_adding_aliases(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_profile_artifacts(artifacts)
    preparer = make_preparer(tmp_path)

    preview = preparer.prepare(artifacts, metadata("Acme"))

    assert "profile_library/acme/manufacturer.json" in {file.path for file in preview.files}
    contents = dict(preparer.render_contents(artifacts, metadata("Acme"), preview))
    assert json.loads(contents["profile_library/acme/manufacturer.json"]) == {"name": "Acme", "aliases": []}


def test_preparer_allows_generated_linear_profile_without_csv(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    artifacts.mkdir()
    (artifacts / "model.json").write_text(
        json.dumps({"name": "Speaker", "calculation_strategy": "linear"}),
        encoding="utf-8",
    )

    preview = make_preparer(tmp_path).prepare(artifacts, metadata(model_id="Speaker 1"))

    assert [file.path for file in preview.files] == ["profile_library/signify/Speaker 1/model.json"]


def test_preparer_blocks_collisions_and_warns_on_duplicates(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts, name="Old lamp")
    preparer = make_preparer(tmp_path)

    preview = preparer.prepare(artifacts, metadata())

    assert preview.warnings == ("Possible duplicate profile: profile_library/signify/LCT010/model.json",)

    collision_metadata = metadata(model_id="LCT010")
    with pytest.raises(ProfilePreparationError, match="Refusing to overwrite"):
        preparer.prepare(artifacts, collision_metadata)


def test_preparer_uses_downloaded_library_index_for_aliases_and_collisions(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library_index(tmp_path, full_name=True, model_aliases=True)
    write_profile_artifacts(artifacts)
    preparer = make_preparer(tmp_path)

    preview = preparer.prepare(artifacts, metadata(model_id="LCT999"))

    assert preview.manufacturer_directory == "signify"
    assert preview.manufacturer_library_url == "https://library.powercalc.nl/manufacturers/signify"
    collision_metadata = metadata(model_id="LCT010")
    with pytest.raises(ProfilePreparationError, match="Refusing to overwrite"):
        preparer.prepare(artifacts, collision_metadata)


@pytest.mark.parametrize(
    "manufacturer, product_name",
    [
        ("Signify", "Signify Hue test lamp"),
        ("Philips", "philips-hue test lamp"),
        ("Philips", "Philips_Hue test lamp"),
    ],
)
def test_preparer_rejects_product_names_prefixed_with_manufacturer_or_alias(
    tmp_path: Path,
    manufacturer: str,
    product_name: str,
) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)

    with pytest.raises(ProfilePreparationError, match="must not start with the manufacturer") as error:
        make_preparer(tmp_path).prepare(artifacts, metadata(manufacturer, product_name=product_name))

    assert error.value.field == "product_name"


def test_preparer_allows_manufacturer_words_outside_the_product_name_prefix(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)

    preview = make_preparer(tmp_path).prepare(
        artifacts,
        metadata(product_name="Mijia Philips Desk Lamp 3"),
    )

    assert preview.manufacturer_directory == "signify"


def test_new_manufacturer_has_no_library_url_and_still_cannot_prefix_product_name(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_profile_artifacts(artifacts)
    preparer = make_preparer(tmp_path)

    preview = preparer.prepare(artifacts, metadata("Acme", product_name="Smart Bulb A19"))
    assert preview.manufacturer_library_url is None

    with pytest.raises(ProfilePreparationError, match="must not start with the manufacturer"):
        preparer.prepare(artifacts, metadata("Acme", product_name="Acme Smart Bulb A19"))


def test_preparer_allows_product_names_starting_with_a_sub_brand_alias(tmp_path: Path) -> None:
    """Aliases are often product lines ("Philips" for Signify, "FRITZ!" for AVM) that
    legitimately open a marketed product name, so only the canonical manufacturer name
    and the name the contributor actually entered may be rejected as a repetition."""
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)

    preview = make_preparer(tmp_path).prepare(
        artifacts,
        metadata(EXISTING_MANUFACTURER, product_name=f"{EXISTING_ALIAS} Hue Go"),
    )

    assert preview.manufacturer_directory == EXISTING_DIRECTORY


def test_preparer_accepts_raw_csv_alongside_gzip_and_rejects_unrelated_artifacts(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)
    (artifacts / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")
    preparer = make_preparer(tmp_path)

    preview = preparer.prepare(artifacts, metadata())

    assert [file.path for file in preview.files].count("profile_library/signify/LCT999/brightness.csv.gz") == 1
    assert "profile_library/signify/LCT999/brightness.csv" not in {file.path for file in preview.files}

    (artifacts / "debug.txt").write_text("not a profile artifact", encoding="utf-8")
    profile_metadata = metadata()
    with pytest.raises(ProfilePreparationError, match="Unexpected artifact"):
        preparer.prepare(artifacts, profile_metadata)


def test_preparer_compresses_raw_csv_for_profile_library(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library(tmp_path)
    write_profile_artifacts(artifacts)
    (artifacts / "brightness.csv.gz").unlink()
    raw_content = b"bri,watt\n1,1.0\n"
    (artifacts / "brightness.csv").write_bytes(raw_content)
    preparer = make_preparer(tmp_path)

    preview = preparer.prepare(artifacts, metadata())
    contents = dict(preparer.render_contents(artifacts, metadata(), preview))

    assert gzip.decompress(contents["profile_library/signify/LCT999/brightness.csv.gz"]) == raw_content


def test_preparer_blocks_case_insensitive_index_collisions(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_library_index(tmp_path)
    write_profile_artifacts(artifacts)
    preparer = make_preparer(tmp_path)

    collision_metadata = metadata(model_id="lct010")
    with pytest.raises(ProfilePreparationError, match="Refusing to overwrite"):
        preparer.prepare(artifacts, collision_metadata)
