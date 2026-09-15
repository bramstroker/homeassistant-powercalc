import json
import os
from pathlib import Path
from unittest.mock import patch

from awesomeversion import AwesomeVersion
import pytest

from custom_components.powercalc.power_profile.error import ProfileDownloadError
from custom_components.powercalc.power_profile.loader.profile_cache import (
    create_staging_directory,
    install_profile,
    read_installed_profile,
)

VERSION = AwesomeVersion("1.0.0")
METADATA = {"id": "model", "hash": "old", "min_version": "1.0.0"}
PROFILE = {"min_version": "1.0.0", "fixed_config": {"power": 3}}


def stage_profile(storage: Path) -> Path:
    staging = create_staging_directory(storage)
    (staging / "model.json").write_text(json.dumps(PROFILE))
    (staging / "hs.csv").write_text("original LUT")
    return staging


@pytest.mark.parametrize("new_revision_present", [False, True])
def test_recovers_interrupted_directory_replacement(tmp_path: Path, new_revision_present: bool) -> None:
    installed = install_profile(tmp_path, stage_profile(tmp_path), METADATA, VERSION)
    previous = tmp_path / ".powercalc" / "previous"
    installed.directory.rename(previous)
    if new_revision_present:
        staging = stage_profile(tmp_path)
        install_profile(tmp_path, staging, {**METADATA, "hash": "new"}, VERSION)
        # Simulate a crash after committing the new revision but before removing the backup.
        previous.mkdir()
        (previous / "model.json").write_text("old revision")

    recovered = read_installed_profile(tmp_path, "model", None, VERSION)
    assert recovered is not None
    assert recovered.metadata["hash"] == ("new" if new_revision_present else "old")
    assert (recovered.directory / "hs.csv").read_text() == "original LUT"
    assert not previous.exists()


def test_failed_directory_replace_restores_previous_revision(tmp_path: Path) -> None:
    original = install_profile(tmp_path, stage_profile(tmp_path), METADATA, VERSION)
    staging = stage_profile(tmp_path)
    (staging / "hs.csv").write_text("replacement LUT")
    real_replace = os.replace

    def fail_install(source: Path, destination: Path) -> None:
        if source == staging:
            raise OSError("cannot replace directory")
        real_replace(source, destination)

    with (
        patch("custom_components.powercalc.power_profile.loader.profile_cache.os.replace", side_effect=fail_install),
        pytest.raises(OSError, match="cannot replace"),
    ):
        install_profile(tmp_path, staging, {**METADATA, "hash": "new"}, VERSION)

    recovered = read_installed_profile(tmp_path, "model", None, VERSION)
    assert recovered.metadata == original.metadata
    assert (recovered.directory / "hs.csv").read_text() == "original LUT"


@pytest.mark.parametrize(
    "damage",
    ["missing_lut", "missing_metadata", "invalid_metadata", "wrong_id", "unsafe_path", "future_metadata"],
)
def test_rejects_incomplete_or_incompatible_installed_revision(tmp_path: Path, damage: str) -> None:
    installed = install_profile(tmp_path, stage_profile(tmp_path), METADATA, VERSION)
    metadata_file = installed.directory / ".installed.json"
    manifest = json.loads(metadata_file.read_text())
    if damage == "missing_lut":
        (installed.directory / "hs.csv").unlink()
    elif damage == "missing_metadata":
        metadata_file.unlink()
    elif damage == "invalid_metadata":
        metadata_file.write_text("{")
    else:
        if damage == "wrong_id":
            manifest["model"]["id"] = "different"
        elif damage == "unsafe_path":
            manifest["resources"] = ["../../outside"]
        else:
            manifest["model"]["min_version"] = "2.0.0"
        metadata_file.write_text(json.dumps(manifest))

    assert read_installed_profile(tmp_path, "model", "new", VERSION) is None


@pytest.mark.parametrize("contents", ["[]", "{", '{"min_version": "2.0.0"}', '{"min_version": "invalid version"}'])
def test_validates_subprofile_json_before_installation(tmp_path: Path, contents: str) -> None:
    original = install_profile(tmp_path, stage_profile(tmp_path), METADATA, VERSION)
    staging = stage_profile(tmp_path)
    (staging / "subprofile").mkdir()
    (staging / "subprofile" / "model.json").write_text(contents)
    with pytest.raises(ProfileDownloadError):
        install_profile(tmp_path, staging, {**METADATA, "hash": "new"}, VERSION)
    recovered = read_installed_profile(tmp_path, "model", None, VERSION)
    assert recovered.metadata == original.metadata


def test_legacy_cache_ignores_abandoned_downloads(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text(json.dumps(PROFILE))
    staging = create_staging_directory(tmp_path)
    (staging / "model.json").write_text("invalid JSON")
    installed = read_installed_profile(tmp_path, "model", "old", VERSION)
    assert installed is not None
    assert installed.metadata["hash"] == "old"
