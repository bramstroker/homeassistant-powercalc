"""Build contribution metadata, draft previews and prepared-job previews."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from measure.contribution.github import (
    GitHubRepository,
)
from measure.contribution.models import ContributionAuthor, ContributionJob, ContributionMetadata, DeviceInfo
from measure.contribution.pull_request import (
    conventional_commit_message,
    deterministic_branch_name,
    profile_pull_request_body,
    pull_request_body,
    pull_request_title,
)
from measure.ha_app.contribution.models import (
    AUTOMATIC_CONTRIBUTION_MESSAGE,
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthStatus,
    ContributionFile,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    contribution_entity_ids,
    supports_automatic_contribution,
)
from measure.profile.model_json import mains_voltage_from_range
from measure.profile.models import RenderedProfileFile
from measure.profile.standby import is_valid_standby_power
from measure.request import MeasurementRequest

MODEL_FILENAME = "model.json"


@dataclass(frozen=True)
class _RequestMetadata:
    manufacturer: str
    model_id: str
    product_name: str | None
    contributor: str
    github_username: str | None
    contributor_email: str | None
    notes: str


def _request_metadata_values(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
    auth: ContributionAuthStatus,
) -> _RequestMetadata:
    if payload is None:
        return _RequestMetadata(
            manufacturer="Unknown",
            model_id=request.model_id,
            product_name=request.product_name,
            contributor=auth.username or "",
            github_username=auth.username,
            contributor_email=None,
            notes="",
        )
    return _RequestMetadata(
        manufacturer=payload.manufacturer_name,
        model_id=payload.model_id,
        product_name=payload.product_name,
        contributor=payload.contributor,
        github_username=payload.contributor_github or auth.username,
        contributor_email=payload.contributor_email,
        notes=payload.notes,
    )


def metadata_from_request(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
    auth: ContributionAuthStatus,
    integration: str | None = None,
) -> ContributionMetadata:
    values = _request_metadata_values(request, payload, auth)
    if not values.github_username:
        raise ContributionApiError(
            ContributionApiErrorCode.INVALID_METADATA,
            "Contributor GitHub username is required",
            field="contributor_github",
        )
    try:
        return ContributionMetadata(
            manufacturer=values.manufacturer,
            model_id=values.model_id,
            product_name=values.product_name,
            measure_type=request.measure_type.value,
            aliases=tuple(payload.aliases) if payload is not None else None,
            gtins=tuple(payload.gtins) if payload is not None else None,
            product_url=payload.product_url if payload is not None else None,
            mains_voltage=payload.mains_voltage if payload is not None else None,
            device_specs=payload.device_specs if payload is not None else None,
            standby_power=payload.standby_power if payload is not None else None,
            standby_power_estimated=payload.standby_power_estimated if payload is not None else None,
            measure_device=_requested_measure_device(request, payload),
            measure_device_firmware=payload.measure_device_firmware if payload is not None else None,
            measure_description=payload.measure_description if payload is not None else None,
            integration=integration,
            notes=values.notes,
            author=ContributionAuthor(
                name=values.contributor,
                github=values.github_username,
                email=values.contributor_email,
            ),
        )
    except ValidationError as error:
        first_error = error.errors()[0]
        field = str(first_error["loc"][0])
        # ProfileAuthor is validated before ContributionMetadata, so its error
        # locations are name/github/email, without an "author" prefix.
        field_names: dict[str, str] = {
            "name": "contributor",
            "github": "contributor_github",
            "email": "contributor_email",
            "manufacturer": "manufacturer_name",
        }
        raise ContributionApiError(
            ContributionApiErrorCode.INVALID_METADATA,
            str(first_error["msg"]).removeprefix("Value error, "),
            field=field_names.get(field, field),
        ) from error


def _requested_measure_device(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
) -> str:
    if payload is None:
        return request.measure_device
    return payload.measure_device or request.measure_device


@dataclass(frozen=True)
class _PreviewContent:
    """The preview fields that differ between a placeholder draft and a prepared job."""

    manufacturer_name: str
    manufacturer_directory: str
    manufacturer_library_url: str | None
    model_id: str
    product_name: str
    contributor: str
    contributor_github: str
    contributor_email: str
    aliases: list[str]
    gtins: list[str]
    product_url: str
    mains_voltage: Literal[120, 230] | None
    voltage_range: dict[str, float] | None
    device_specs: dict[str, Any] | None
    device_type: str
    standby_power: float | None
    standby_power_estimated: bool
    measure_device: str
    measure_device_firmware: str
    measure_description: str
    integration: str | None
    commit_message: str
    pr_title: str
    pr_body: str
    branch_name: str
    job_id: str | None
    warnings: list[str]


def draft_from_request(
    *,
    session_id: str,
    request: MeasurementRequest,
    artifact_root: Path,
    auth: ContributionAuthStatus,
    integration: str | None = None,
    manufacturer: str | None = None,
    default_connectivity: str | None = None,
    default_model_id: str | None = None,
    default_measure_device_firmware: str | None = None,
    default_contributor_name: str | None = None,
    default_contributor_github: str | None = None,
    default_contributor_email: str | None = None,
) -> ContributionPreviewResponse:
    """Build a placeholder preview, before a contribution job exists."""
    files = _list_draft_files(artifact_root)
    reason = _contribution_ineligibility_reason(request, artifact_root, files)
    artifact_model = _artifact_model(artifact_root)
    voltage_range = _voltage_range(artifact_model)
    author = _first_author(artifact_model)
    device_specs = _artifact_device_specs(artifact_model)
    if default_connectivity is not None and "connectivity" not in (device_specs or {}):
        device_specs = {**(device_specs or {}), "connectivity": [default_connectivity]}
    content = _PreviewContent(
        manufacturer_name=manufacturer or "",
        manufacturer_directory="",
        manufacturer_library_url=None,
        model_id=request.model_id or default_model_id or "",
        product_name=request.product_name,
        contributor=str(author.get("name") or default_contributor_name or auth.username or ""),
        contributor_github=str(author.get("github") or default_contributor_github or auth.username or ""),
        contributor_email=str(author.get("email") or default_contributor_email or ""),
        aliases=_string_list(artifact_model.get("aliases")),
        gtins=_string_list(artifact_model.get("gtin")),
        product_url=str(artifact_model.get("product_url") or ""),
        mains_voltage=_model_mains_voltage(artifact_model),
        voltage_range=voltage_range,
        device_specs=device_specs,
        device_type=str(artifact_model.get("device_type") or ""),
        standby_power=artifact_model.get("standby_power")
        if is_valid_standby_power(artifact_model.get("standby_power"))
        else None,
        standby_power_estimated=artifact_model.get("standby_power_estimated") is True,
        measure_device=str(artifact_model.get("measure_device") or request.measure_device),
        measure_device_firmware=str(
            artifact_model.get("measure_device_firmware") or default_measure_device_firmware or ""
        ),
        measure_description=str(artifact_model.get("measure_description") or ""),
        integration=integration,
        commit_message=f"feat(profile): add {request.model_id}",
        pr_title=f"Add {request.model_id} power profile",
        pr_body=profile_pull_request_body(
            DeviceInfo(
                manufacturer=manufacturer or "Unknown",
                model_id=request.model_id,
                product_name=request.product_name,
                integration=integration,
            ),
            measure_device=request.measure_device,
            measure_type=request.measure_type.value,
            notes="",
            file_paths=[file.path for file in files],
        ),
        branch_name="",
        job_id=None,
        warnings=[],
    )
    return _build_preview_response(
        session_id=session_id,
        request=request,
        files=files,
        eligible=reason is None,
        reason=reason,
        content=content,
    )


def _contribution_ineligibility_reason(
    request: MeasurementRequest,
    artifact_root: Path,
    files: list[ContributionFile],
) -> str | None:
    if not supports_automatic_contribution(request):
        return AUTOMATIC_CONTRIBUTION_MESSAGE
    has_model = artifact_root.is_dir() and any(Path(file.path).name == MODEL_FILENAME for file in files)
    return None if has_model else f"Contribution requires a generated {MODEL_FILENAME} artifact"


def _artifact_device_specs(model: dict[str, Any]) -> dict[str, Any] | None:
    value = model.get("device_specs")
    return value if isinstance(value, dict) else None


def preview_from_job(
    *,
    session_id: str,
    request: MeasurementRequest,
    job: ContributionJob,
    notes: str,
    contents: list[RenderedProfileFile],
    base_sha: str,
    fork_owner: str | None,
    repository: GitHubRepository,
) -> ContributionPreviewResponse:
    content_by_path = {file.path: file.content for file in contents}
    prepared_model = _prepared_model(contents)
    content = _PreviewContent(
        manufacturer_name=job.metadata.manufacturer,
        manufacturer_directory=job.preview.manufacturer_directory,
        manufacturer_library_url=job.preview.manufacturer_library_url,
        model_id=job.metadata.model_id,
        product_name=job.metadata.product_name or request.product_name,
        contributor=job.metadata.author.name,
        contributor_github=job.metadata.author.github,
        contributor_email=job.metadata.author.email or "",
        aliases=list(job.metadata.aliases or ()),
        gtins=list(job.metadata.gtins or ()),
        product_url=job.metadata.product_url or "",
        mains_voltage=_model_mains_voltage(prepared_model),
        voltage_range=_voltage_range(prepared_model),
        device_specs=job.metadata.device_specs,
        device_type=str(prepared_model.get("device_type") or ""),
        standby_power=job.preview.standby_power,
        standby_power_estimated=prepared_model.get("standby_power_estimated") is True,
        measure_device=job.metadata.measure_device or request.measure_device,
        measure_device_firmware=job.metadata.measure_device_firmware or "",
        measure_description=job.metadata.measure_description or "",
        integration=job.metadata.integration,
        commit_message=conventional_commit_message(job.preview),
        pr_title=pull_request_title(job.preview),
        pr_body=pull_request_body(job),
        branch_name=deterministic_branch_name(job.preview),
        job_id=job.id,
        warnings=list(job.preview.warnings),
    )
    return _build_preview_response(
        session_id=session_id,
        request=request,
        files=[_build_preview_file(file.path, content_by_path[file.path]) for file in job.preview.files],
        eligible=True,
        reason=None,
        content=content,
        notes=notes,
        base_sha=base_sha,
        fork_owner=fork_owner,
        repository=repository,
    )


def _build_preview_response(
    *,
    session_id: str,
    request: MeasurementRequest,
    files: list[ContributionFile],
    eligible: bool,
    reason: str | None,
    content: _PreviewContent,
    notes: str = "",
    base_sha: str | None = None,
    fork_owner: str | None = None,
    repository: GitHubRepository | None = None,
) -> ContributionPreviewResponse:
    repository = repository or GitHubRepository.from_environment()
    device_info: dict[str, str | int | float | bool | None] = {
        "manufacturer": content.manufacturer_name,
        "model_id": content.model_id,
        "product_name": content.product_name,
        "measure_device": content.measure_device,
    }
    home_assistant_info: dict[str, str | int | float | bool | None] = {
        "measure_type": request.measure_type.value,
        "controlled_entity": ", ".join(contribution_entity_ids(request)) or None,
        "integration": content.integration,
    }
    return ContributionPreviewResponse(
        session_id=session_id,
        eligible=eligible,
        reason=reason,
        repository=repository.full_name,
        fork_repository=f"{fork_owner}/{repository.name}" if fork_owner else None,
        base_branch=repository.branch,
        base_sha=base_sha,
        manufacturer_name=content.manufacturer_name,
        manufacturer_directory=content.manufacturer_directory,
        manufacturer_library_url=content.manufacturer_library_url,
        model_id=content.model_id,
        product_name=content.product_name,
        contributor=content.contributor,
        contributor_github=content.contributor_github,
        contributor_email=content.contributor_email,
        aliases=content.aliases,
        gtins=content.gtins,
        product_url=content.product_url,
        mains_voltage=content.mains_voltage,
        voltage_range=content.voltage_range,
        device_specs=content.device_specs,
        device_type=content.device_type,
        standby_power=content.standby_power,
        standby_power_estimated=content.standby_power_estimated,
        measure_device=content.measure_device,
        measure_device_firmware=content.measure_device_firmware,
        measure_description=content.measure_description,
        device_info=device_info,
        home_assistant=home_assistant_info,
        notes=notes,
        files=files,
        commit_message=content.commit_message,
        pr_title=content.pr_title,
        pr_body=content.pr_body,
        branch_name=content.branch_name,
        job_id=content.job_id,
        model_json=next(
            (file.rendered_json for file in files if Path(file.path).name == MODEL_FILENAME),
            None,
        ),
        warnings=content.warnings,
    )


def _list_draft_files(artifact_root: Path) -> list[ContributionFile]:
    if not artifact_root.is_dir():
        return []
    return [
        ContributionFile(name=path.name, path=path.name, size=path.stat().st_size)
        for path in sorted(artifact_root.iterdir())
        if path.is_file() and not path.is_symlink()
    ]


def _artifact_model(artifact_root: Path) -> dict[str, Any]:
    try:
        value = json.loads((artifact_root / MODEL_FILENAME).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _voltage_range(model: dict[str, Any]) -> dict[str, float] | None:
    value = model.get("voltage_range")
    if not isinstance(value, dict):
        return None
    minimum = value.get("min")
    maximum = value.get("max")
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int | float)
        or not isinstance(maximum, int | float)
        or minimum > maximum
    ):
        return None
    return {"min": float(minimum), "max": float(maximum)}


def _model_mains_voltage(model: dict[str, Any]) -> Literal[120, 230] | None:
    derived = mains_voltage_from_range(model.get("voltage_range"))
    if derived is not None:
        return derived
    value = model.get("mains_voltage")
    if isinstance(value, bool) or value not in (120, 230):
        return None
    return 120 if value == 120 else 230


def _prepared_model(contents: list[RenderedProfileFile]) -> dict[str, Any]:
    content = next((file.content for file in contents if Path(file.path).name == MODEL_FILENAME), None)
    if content is None:
        return {}
    try:
        value = json.loads(content)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _first_author(model: dict[str, Any]) -> dict[str, Any]:
    authors = model.get("authors")
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        return authors[0]
    return {}


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _build_preview_file(path: str, content: bytes) -> ContributionFile:
    rendered_json: Any | None = None
    text: str | None = None
    if path.endswith(".json"):
        rendered_json = json.loads(content)
    elif not path.endswith((".gz", ".png")):
        text = content.decode("utf-8")
    return ContributionFile(
        name=Path(path).name,
        path=path,
        size=len(content),
        content=text,
        rendered_json=rendered_json,
    )
