from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from measure.profile.models import ProfileAuthor, ProfileMetadata


class ContributionErrorCode(StrEnum):
    INVALID_ARTIFACTS = "invalid_artifacts"
    VALIDATION_FAILED = "validation_failed"
    PATH_COLLISION = "path_collision"
    MISSING_CREDENTIALS = "missing_credentials"
    GITHUB_ERROR = "github_error"
    JOB_NOT_FOUND = "job_not_found"


class ContributionJobStatus(StrEnum):
    """Lifecycle of one contribution job, persisted per job in the ``ContributionJobStore``.

    The app-level ``measure.ha_app.contribution.models.ContributionState`` is derived
    from this plus UI context; this enum is the authoritative record of what happened
    to a specific prepared submission.
    """

    PREVIEWED = "previewed"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    FAILED = "failed"


class ContributionError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ContributionErrorCode
    message: str = Field(min_length=1)
    detail: str | None = None


ContributionAuthor = ProfileAuthor


class ContributionMetadata(ProfileMetadata):
    """Profile metadata plus context used only while creating a pull request."""

    measure_type: str | None = Field(default=None, max_length=50)
    #: Home Assistant integration the measured entity is provided by.
    integration: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=2_000)
    author: ContributionAuthor

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str) -> str:
        return value.strip()


class DeviceInfo(BaseModel):
    """Identity of the device under measurement, as rendered into the pull request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manufacturer: str
    model_id: str
    product_name: str
    #: Home Assistant integration the measured entity is provided by.
    integration: str | None = None


class ContributionPreparedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha: str | None = None


class ContributionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manufacturer_directory: str
    manufacturer_library_url: str | None = None
    model_directory: str
    files: tuple[ContributionPreparedFile, ...]
    warnings: tuple[str, ...] = ()


class ContributionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    branch: str
    commit_sha: str
    pull_request_url: str
    pull_request_number: int | None = None


class ContributionJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    status: ContributionJobStatus
    metadata: ContributionMetadata
    preview: ContributionPreview
    base_sha: str | None = None
    created_at: str
    updated_at: str
    error: ContributionError | None = None
    submission: ContributionSubmission | None = None
