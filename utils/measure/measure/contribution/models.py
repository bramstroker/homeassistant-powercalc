from __future__ import annotations

from enum import StrEnum
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ContributionAuthor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    github: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=200)

    @field_validator("name", "github")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ContributionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manufacturer: str = Field(min_length=1, max_length=200)
    manufacturer_directory: str | None = Field(default=None, min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=120)
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    measure_type: str | None = Field(default=None, max_length=50)
    measure_device: str | None = Field(default=None, max_length=200)
    notes: str = Field(default="", max_length=2_000)
    author: ContributionAuthor

    @field_validator("manufacturer", "manufacturer_directory", "model_id", "product_name")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", value):
            raise ValueError("model_id contains unsafe characters")
        return value

    @field_validator("manufacturer_directory")
    @classmethod
    def validate_manufacturer_directory(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value in {".", ".."} or not re.fullmatch(r"[a-z0-9][a-z0-9 ._()+-]*", value):
            raise ValueError("manufacturer_directory contains unsafe characters")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str) -> str:
        return value.strip()


class ContributionPreparedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha: str | None = None


class ContributionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manufacturer_directory: str
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
