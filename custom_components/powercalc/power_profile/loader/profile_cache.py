"""Persist complete installed profiles independently of the remote library index."""

from dataclasses import dataclass
import gzip
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, cast

from awesomeversion import AwesomeVersion, AwesomeVersionException

from custom_components.powercalc.power_profile.error import ProfileDownloadError

_LOGGER = logging.getLogger(__name__)
CACHE_DIRECTORY = ".powercalc"
METADATA_FILE = ".installed.json"


def _sync_directory(directory: Path) -> None:
    """Persist a directory entry, so a completed rename survives an unclean shutdown."""
    try:
        directory_descriptor = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - directories cannot be opened on all platforms
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:  # pragma: no cover - directory fsync is not supported on all platforms
        pass
    finally:
        os.close(directory_descriptor)


def save_resource(data: bytes, path: Path) -> None:
    """Atomically save a downloaded resource to the local profile storage directory.

    The contents are flushed to disk before the rename, and the directory entry is flushed
    after it. Without both, a power loss shortly after an update can leave the new file name
    pointing at unwritten data, which is how a cached profile ends up as invalid JSON.
    """
    os.makedirs(path.parent, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as file_handle:
            file_handle.write(data)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, path)
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


@dataclass
class InstalledProfile:
    """A usable cached revision and the discovery metadata belonging to it."""

    metadata: dict[str, Any]
    directory: Path


def compress_installed_profile_csv_files(installed: InstalledProfile) -> None:
    """Replace plain CSV resources in an installed profile with gzip files.

    Gzip files are written before the installation manifest is switched to their
    paths. The raw files are only removed afterwards, so an interrupted migration
    always leaves either the old or the new resource set usable.
    """
    csv_paths = sorted(installed.directory.rglob("*.csv"))
    if not csv_paths:
        return

    for csv_path in csv_paths:
        compressed_path = csv_path.with_name(f"{csv_path.name}.gz")
        save_resource(gzip.compress(csv_path.read_bytes(), mtime=0), compressed_path)

    metadata_path = installed.directory / METADATA_FILE
    if metadata_path.exists():
        manifest = json.loads(metadata_path.read_bytes())
        resources: list[str] = []
        for resource in manifest["resources"]:
            normalized_resource = f"{resource}.gz" if str(resource).endswith(".csv") else resource
            if normalized_resource not in resources:
                resources.append(normalized_resource)
        manifest["resources"] = resources
        save_resource(json.dumps(manifest).encode(), metadata_path)

    for csv_path in csv_paths:
        csv_path.unlink()


def validate_profile(directory: Path, version: AwesomeVersion) -> dict[str, Any]:
    """Validate JSON and version requirements before accepting any downloaded files."""
    try:
        model = json.loads((directory / "model.json").read_bytes())
        for path in directory.rglob("model.json"):
            if CACHE_DIRECTORY in path.relative_to(directory).parts:
                continue
            data = json.loads(path.read_bytes())
            if not isinstance(data, dict):
                raise ValueError("model.json must contain an object")
            minimum = data.get("min_version")
            if minimum and AwesomeVersion(minimum) > version:
                raise ValueError(f"profile requires Powercalc {minimum} (installed: {version})")
    except (OSError, ValueError, TypeError, AwesomeVersionException) as err:
        raise ProfileDownloadError(f"Installed profile is unusable: {err}") from err
    return cast(dict[str, Any], model)


def recover_installation(storage: Path) -> None:
    """Recover a directory replacement interrupted before the new revision was installed."""
    cache = storage / CACHE_DIRECTORY
    current, previous = cache / "current", cache / "previous"
    if previous.exists():
        if current.exists():
            shutil.rmtree(previous)
        else:
            os.replace(previous, current)
        _sync_directory(cache)


def read_installed_profile(
    storage: Path, model_id: str, legacy_hash: str | None, version: AwesomeVersion
) -> InstalledProfile | None:
    """Read installed metadata; bootstrap old caches from their own model.json, never the latest index."""
    recover_installation(storage)
    current = storage / CACHE_DIRECTORY / "current"
    directory = current if current.exists() else storage
    if not (directory / "model.json").exists():
        return None
    try:
        model = validate_profile(directory, version)
        metadata_path = directory / METADATA_FILE
        if directory == current or metadata_path.exists():
            metadata = _read_installed_metadata(directory, model_id)
        else:
            metadata = {
                key: model[key]
                for key in ("name", "aliases", "legacy_ids", "device_type", "discovery_by")
                if key in model
            }
            metadata.update(id=model_id, hash=legacy_hash)
        # The installed files are authoritative, including after an integration downgrade.
        if (minimum := metadata.get("min_version")) and AwesomeVersion(minimum) > version:
            raise ValueError(f"installed metadata requires Powercalc {minimum}")
        if minimum := model.get("min_version"):
            metadata["min_version"] = minimum
        return InstalledProfile(metadata, directory)
    except (ProfileDownloadError, OSError, ValueError, KeyError, TypeError, AwesomeVersionException) as err:
        _LOGGER.warning("Cannot use cached profile %s: %s", storage, err)
        return None


def _read_installed_metadata(directory: Path, model_id: str) -> dict[str, Any]:
    """Read the installed manifest and verify that all recorded resources still exist."""
    manifest = json.loads((directory / METADATA_FILE).read_bytes())
    metadata = manifest["model"]
    if not isinstance(metadata, dict) or metadata.get("id") != model_id:
        raise ValueError("invalid installed model metadata")

    profile_root = directory.resolve()
    for resource in manifest["resources"]:
        path = (profile_root / resource).resolve()
        if not path.is_relative_to(profile_root) or not path.is_file():
            raise ValueError("installed profile has missing or invalid resources")
    return metadata


def create_staging_directory(storage: Path) -> Path:
    """Create a temporary download directory on the same filesystem as the installed profile."""
    cache = storage / CACHE_DIRECTORY
    cache.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="download-", dir=cache))


def install_profile(
    storage: Path, staging: Path, metadata: dict[str, Any], version: AwesomeVersion
) -> InstalledProfile:
    """Commit the complete profile and its metadata together, with recovery after an interrupted rename."""
    validate_profile(staging, version)
    resources = [str(path.relative_to(staging)) for path in staging.rglob("*") if path.is_file()]
    manifest = {"model": metadata, "resources": resources}
    save_resource(json.dumps(manifest).encode(), staging / METADATA_FILE)
    recover_installation(storage)
    cache = storage / CACHE_DIRECTORY
    current, previous = cache / "current", cache / "previous"
    if current.exists():
        os.replace(current, previous)
        _sync_directory(cache)
    try:
        os.replace(staging, current)
        _sync_directory(cache)
    except OSError:
        recover_installation(storage)
        raise
    if previous.exists():
        shutil.rmtree(previous, ignore_errors=True)
    return InstalledProfile(dict(metadata), current)
