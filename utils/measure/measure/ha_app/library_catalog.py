from collections.abc import Callable
from typing import cast

import requests

LIBRARY_ENDPOINT = "https://api.powercalc.nl/library"
LIBRARY_TIMEOUT_SECONDS = 15

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


class MeasureDeviceCatalog:
    """Load canonical measurement-device names from the published profile library."""

    def __init__(
        self,
        *,
        loader: LibraryLoader | None = None,
    ) -> None:
        self._loader = loader or _load_published_library

    def devices(self) -> tuple[str, ...]:
        try:
            return extract_measure_devices(self._loader())
        except Exception as error:
            raise LibraryCatalogError("Could not load measurement devices from the Powercalc library") from error


def extract_measure_devices(library: object) -> tuple[str, ...]:
    if not isinstance(library, dict):
        raise LibraryCatalogError("Powercalc library response must be a JSON object")
    manufacturers = library.get("manufacturers")
    if not isinstance(manufacturers, list):
        raise LibraryCatalogError("Powercalc library response has no manufacturers list")

    devices: dict[str, str] = {}
    for manufacturer in manufacturers:
        if not isinstance(manufacturer, dict):
            continue
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


def _load_published_library() -> object:
    response = requests.get(LIBRARY_ENDPOINT, timeout=LIBRARY_TIMEOUT_SECONDS)
    response.raise_for_status()
    return cast(object, response.json())
