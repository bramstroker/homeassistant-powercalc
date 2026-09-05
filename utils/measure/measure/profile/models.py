import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileAuthor(BaseModel):
    """Contributor attribution written to ``model.json``."""

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
        normalized = value.strip() or None
        if normalized and not _valid_email(normalized):
            raise ValueError("Enter a valid email address, for example name@example.com.")
        return normalized


class ProfileMetadata(BaseModel):
    """Editable metadata used to turn raw measurement artifacts into a profile.

    Optional values are only applied when supplied. This lets a frontend prefill the
    form from the generated ``model.json`` without the preparation operation erasing
    metadata already present in that file.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    manufacturer: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=120)
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: tuple[str, ...] | None = None
    gtins: tuple[str, ...] | None = None
    product_url: str | None = Field(default=None, max_length=2_000)
    mains_voltage: Literal[120, 230] | None = None
    device_specs: dict[str, Any] | None = None
    measure_device: str | None = Field(default=None, max_length=200)
    measure_device_firmware: str | None = Field(default=None, max_length=200)
    measure_description: str | None = Field(default=None, max_length=2_000)
    author: ProfileAuthor | None = None

    @field_validator("manufacturer", "model_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("product_name")
    @classmethod
    def normalize_product_name(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator(
        "product_url",
        "measure_device",
        "measure_device_firmware",
        "measure_description",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Keep explicit blank edits distinct from omitted metadata. The preparer
        # removes blank optional fields from model.json after applying the edits.
        return value.strip()

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", value):
            raise ValueError("model_id contains unsafe characters")
        return value

    @field_validator("aliases")
    @classmethod
    def normalize_string_list(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        return tuple(dict.fromkeys(item.strip() for item in value if item.strip()))

    @field_validator("gtins")
    @classmethod
    def validate_gtins(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        normalized = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
        invalid = next((item for item in normalized if not re.fullmatch(r"\d{8}|\d{12,14}", item, re.ASCII)), None)
        if invalid is not None:
            raise ValueError(f"invalid GTIN: {invalid}")
        return normalized

    @field_validator("product_url")
    @classmethod
    def validate_product_url(cls, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise ValueError("product_url must use https://")
        return value


def _valid_email(value: str) -> bool:
    if any(character.isspace() for character in value) or value.count("@") != 1:
        return False
    local, domain = value.split("@")
    host, separator, suffix = domain.rpartition(".")
    return bool(local and host and separator and suffix)
