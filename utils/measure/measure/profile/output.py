import io
import os
from pathlib import Path
import tempfile
import zipfile

from measure.contribution.models import ContributionPreview
from measure.contribution.prepare import ProfilePreparationError, ProfilePreparer
from measure.profile.models import ProfileMetadata


def prepared_profile_archive(contents: tuple[tuple[str, bytes], ...]) -> bytes:
    """Return prepared profile files as a reproducible ZIP archive."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path, content in contents:
            info = zipfile.ZipInfo(relative_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def write_prepared_profile(
    *,
    preparer: ProfilePreparer,
    artifact_directory: Path,
    metadata: ProfileMetadata,
    output_directory: Path,
) -> ContributionPreview:
    """Validate, render, and atomically write a prepared profile package.

    Raw measurement artifacts are only read. The returned directory contains the
    actual ``profile_library/<manufacturer>/<model>`` layout, ready to inspect or
    copy into a checkout.
    """

    artifact_directory = artifact_directory.resolve()
    output_directory = output_directory.resolve()
    preview = preparer.prepare(artifact_directory, metadata)
    contents = preparer.render_contents(artifact_directory, metadata, preview)

    destinations = tuple((_safe_destination(output_directory, relative), content) for relative, content in contents)
    for destination, _content in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
    for destination, content in destinations:
        _atomic_write(destination, content)
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
