"""Bounded, privacy-conscious attributes for vacuum profile recordings."""

from collections.abc import Mapping
import math

MAX_ATTRIBUTE_STRING_LENGTH = 512
EXCLUDED_ATTRIBUTES = frozenset(
    {"access_token", "ap", "bssid", "entity_picture", "friendly_name", "ip", "latitude", "longitude", "ssid", "token"},
)


def vacuum_recording_attributes(attributes: Mapping[str, object]) -> dict[str, object]:
    """Keep scalar analysis inputs, excluding payloads and identifying metadata."""
    return {key: value for key, value in attributes.items() if key not in EXCLUDED_ATTRIBUTES and _recordable(value)}


def _recordable(value: object) -> bool:
    if isinstance(value, str):
        return len(value) <= MAX_ATTRIBUTE_STRING_LENGTH and not value.startswith(("http://", "https://", "data:"))
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, bool | int)


def vacuum_attribute_policy() -> dict[str, object]:
    return {
        "types": ["string", "boolean", "integer", "finite_float"],
        "max_string_length": MAX_ATTRIBUTE_STRING_LENGTH,
        "excluded_attributes": sorted(EXCLUDED_ATTRIBUTES),
        "exclude_url_values": True,
    }
