import io
import os
from pathlib import Path
import tempfile
import zipfile

from measure.profile.models import ProfileMetadata, ProfilePreview, RenderedProfileFile
from measure.profile.prepare import ProfilePreparationError, ProfilePreparer


def prepared_profile_archive(contents: list[RenderedProfileFile]) -> bytes:
    """Return prepared profile files as a reproducible ZIP archive."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in contents:
            info = zipfile.ZipInfo(file.path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, file.content)
    return output.getvalue()


def write_prepared_profile(
    *,
    preparer: ProfilePreparer,
    artifact_directory: Path,
    metadata: ProfileMetadata,
    output_directory: Path,
) -> ProfilePreview:
    """Validate, render, and atomically write a prepared profile package.

    Raw measurement artifacts are only read. The returned directory contains the
    actual ``profile_library/<manufacturer>/<model>`` layout, ready to inspect or
    copy into a checkout.
    """

    artifact_directory = artifact_directory.resolve()
    output_directory = output_directory.resolve()
    preview = preparer.prepare(artifact_directory, metadata)
    contents = preparer.render_contents(artifact_directory, metadata, preview)

    destinations = [_safe_destination(output_directory, file.path) for file in contents]
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
    for destination, file in zip(destinations, contents, strict=True):
        _atomic_write(destination, file.content)
    return preview


def _safe_destination(output_directory: Path, relative_path: str) -> Path:
    destination = (output_directory / relative_path).resolve()
    if not destination.is_relative_to(output_directory):
        raise ProfilePreparationError(f"Prepared file path escapes the output directory: {relative_path}")
    return destination


def _atomic_write(destination: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as file:
        temporary_path = Path(file.name)
        file.write(content)
    try:
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
