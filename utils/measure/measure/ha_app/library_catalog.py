from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import cast

import requests

from measure.profile.specifications import DeviceSpecField, device_spec_fields

LIBRARY_ENDPOINT = "https://api.powercalc.nl/library"
FULL_LIBRARY_ENDPOINT = "https://api.powercalc.nl/library/full"
MODEL_SCHEMA_ENDPOINT = (
    "https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/profile_library/model_schema.json"
)
LIBRARY_TIMEOUT_SECONDS = 15
#: Matches the Cache-Control window the catalog endpoints advertise to browsers.
LIBRARY_CACHE_SECONDS = 600

_NON_DEVICE_VALUES = frozenset(
    {
        "from manufacturer specifications",
        "n/a",
        "see linked profile",
    },
)


class LibraryCatalogError(RuntimeError):
    """Raised when the published profile library cannot provide a usable catalog."""


LibraryLoader = Callable[[], object]


class _CachedLoader:
    """Reuse one library response across catalogs and requests until it goes stale.

    The catalogs are consulted per measured entity while preparing a profile, and the full
    library alone is several hundred kilobytes, so refetching it every time would dominate
    the request. Only the default loaders are wrapped; an injected loader is left alone.
    """

    def __init__(self, loader: LibraryLoader, ttl: float = LIBRARY_CACHE_SECONDS) -> None:
        self._loader = loader
        self._ttl = ttl
        self._lock = Lock()
        self._value: object = None
        self._loaded_at = 0.0

    def __call__(self) -> object:
        with self._lock:
            now = monotonic()
            if self._value is None or now - self._loaded_at >= self._ttl:
                self._value = self._loader()
                self._loaded_at = now
            return self._value


class MeasureDeviceCatalog:
    """Load canonical measurement-device names from the published profile library."""

    def __init__(
        self,
        *,
        loader: LibraryLoader | None = None,
    ) -> None:
        self._loader = loader or _cached_full_library

    def devices(self) -> tuple[str, ...]:
        try:
            return extract_measure_devices(self._loader())
        except Exception as error:
            raise LibraryCatalogError("Could not load measurement devices from the Powercalc library") from error


class ManufacturerCatalog:
    """Load manufacturer names users can select while preparing a profile."""

    def __init__(self, *, loader: LibraryLoader | None = None) -> None:
        self._loader = loader or _cached_library

    def manufacturers(self) -> tuple[str, ...]:
        try:
            return extract_manufacturers(self._loader())
        except Exception as error:
            raise LibraryCatalogError("Could not load manufacturers from the Powercalc library") from error

    def canonical_name(self, value: str) -> str:
        """Resolve a Home Assistant manufacturer name through library names and aliases."""
        try:
            return resolve_manufacturer_name(self._loader(), value)
        except Exception as error:
            raise LibraryCatalogError("Could not load manufacturers from the Powercalc library") from error


class DeviceSpecificationCatalog:
    """Load schema-backed ``device_specs`` fields for every device type."""

    def __init__(self, *, loader: LibraryLoader | None = None) -> None:
        self._loader = loader or _cached_model_schema

    def fields(self) -> dict[str, tuple[DeviceSpecField, ...]]:
        try:
            schema = self._loader()
            if not isinstance(schema, dict):
                raise TypeError("model schema must be an object")
            return device_spec_fields(schema)
        except Exception as error:
            raise LibraryCatalogError("Could not load device specifications from model_schema.json") from error


def extract_manufacturers(library: object) -> tuple[str, ...]:
    manufacturers = _manufacturer_entries(library)
    names: dict[str, str] = {}
    for manufacturer in manufacturers:
        value = manufacturer.get("full_name") or manufacturer.get("name")
        if not isinstance(value, str) or not (name := value.strip()):
            continue
        names.setdefault(name.casefold(), name)
    return tuple(sorted(names.values(), key=str.casefold))


def resolve_manufacturer_name(library: object, value: str) -> str:
    """Return the canonical library name for a known, unambiguous manufacturer value."""
    candidate = value.strip()
    if not candidate:
        return candidate
    direct_names, aliases = _manufacturer_name_indexes(_manufacturer_entries(library))
    key = candidate.casefold()
    if resolved := direct_names.get(key):
        return resolved
    alias_matches = aliases.get(key, set())
    return next(iter(alias_matches)) if len(alias_matches) == 1 else candidate


def _manufacturer_name_indexes(
    manufacturers: list[dict[str, object]],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    direct_names: dict[str, str] = {}
    aliases: dict[str, set[str]] = {}
    for manufacturer in manufacturers:
        canonical = _canonical_manufacturer_name(manufacturer)
        if canonical is None:
            continue
        for direct_value in (manufacturer.get("name"), manufacturer.get("full_name")):
            if isinstance(direct_value, str) and (name := direct_value.strip()):
                direct_names.setdefault(name.casefold(), canonical)
        for alias in _manufacturer_aliases(manufacturer):
            aliases.setdefault(alias.casefold(), set()).add(canonical)
    return direct_names, aliases


def _canonical_manufacturer_name(manufacturer: dict[str, object]) -> str | None:
    value = manufacturer.get("full_name") or manufacturer.get("name")
    return value.strip() or None if isinstance(value, str) else None


def _manufacturer_aliases(manufacturer: dict[str, object]) -> tuple[str, ...]:
    values = manufacturer.get("aliases")
    if not isinstance(values, list):
        return ()
    return tuple(alias for value in values if isinstance(value, str) and (alias := value.strip()))


def extract_measure_devices(library: object) -> tuple[str, ...]:
    manufacturers = _manufacturer_entries(library)

    devices: dict[str, str] = {}
    for manufacturer in manufacturers:
        models = manufacturer.get("models")
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict):
                continue
            value = model.get("measure_device")
            if not isinstance(value, str):
                continue
            name = value.strip()
            key = name.casefold()
            if name and key not in _NON_DEVICE_VALUES:
                devices.setdefault(key, name)
    return tuple(sorted(devices.values(), key=str.casefold))


def _manufacturer_entries(library: object) -> list[dict[str, object]]:
    if not isinstance(library, dict):
        raise LibraryCatalogError("Powercalc library response must be a JSON object")
    manufacturers = library.get("manufacturers")
    if not isinstance(manufacturers, list):
        raise LibraryCatalogError("Powercalc library response has no manufacturers list")
    return [manufacturer for manufacturer in manufacturers if isinstance(manufacturer, dict)]


def _load_published_library() -> object:
    return _load_library(LIBRARY_ENDPOINT)


def _load_full_published_library() -> object:
    return _load_library(FULL_LIBRARY_ENDPOINT)


def _load_published_model_schema() -> object:
    return _load_library(MODEL_SCHEMA_ENDPOINT)


def _load_library(endpoint: str) -> object:
    response = requests.get(endpoint, timeout=LIBRARY_TIMEOUT_SECONDS)
    response.raise_for_status()
    return cast(object, response.json())


_cached_library = _CachedLoader(_load_published_library)
_cached_full_library = _CachedLoader(_load_full_published_library)
_cached_model_schema = _CachedLoader(_load_published_model_schema)
