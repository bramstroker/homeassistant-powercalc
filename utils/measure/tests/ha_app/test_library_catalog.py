from unittest.mock import MagicMock

from measure.ha_app import library_catalog
from measure.ha_app.library_catalog import (
    FULL_LIBRARY_ENDPOINT,
    DeviceSpecificationCatalog,
    LibraryCatalogError,
    ManufacturerCatalog,
    MeasureDeviceCatalog,
    _CachedLoader,
    _load_published_library,
    _load_published_model_schema,
    extract_manufacturers,
    extract_measure_devices,
    resolve_manufacturer_name,
)
import pytest


def test_measure_device_catalog_uses_full_library_metadata_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[tuple[str, int]] = []

    class Response:
        @staticmethod
        def raise_for_status() -> None:
            pass

        @staticmethod
        def json() -> object:
            return {"manufacturers": [{"models": [{"measure_device": "Shelly Plug S"}]}]}

    def get(url: str, *, timeout: int) -> Response:
        requested.append((url, timeout))
        return Response()

    monkeypatch.setattr(library_catalog.requests, "get", get)

    assert MeasureDeviceCatalog().devices() == ["Shelly Plug S"]
    assert requested == [(FULL_LIBRARY_ENDPOINT, 15)]


def test_extract_measure_devices_returns_canonical_unique_hardware_names() -> None:
    library = {
        "manufacturers": [
            {
                "models": [
                    {"measure_device": " Shelly Plug S "},
                    {"measure_device": "shelly plug s"},
                    {"measure_device": "N/A"},
                    {"measure_device": "From manufacturer specifications"},
                    {"measure_device": "TP-Link Kasa KP115"},
                    {"measure_device": None},
                    {"measure_device": " "},
                    "invalid",
                ],
            },
            {"models": [{"measure_device": "See linked profile"}]},
            {"models": "invalid"},
            "invalid",
        ],
    }

    assert extract_measure_devices(library) == ["Shelly Plug S", "TP-Link Kasa KP115"]


def test_extract_manufacturers_prefers_full_names_and_removes_case_duplicates() -> None:
    library = {
        "manufacturers": [
            {"name": "signify", "full_name": "Signify", "models": []},
            {"name": "SIGNIFY", "models": []},
            {"name": " IKEA ", "models": []},
            {"name": "", "models": []},
            {"name": " "},
            {"name": 42},
            "invalid",
        ],
    }

    assert extract_manufacturers(library) == ["IKEA", "Signify"]


def test_catalog_collections_do_not_modify_the_loaded_library() -> None:
    library = {"manufacturers": [{"name": "Shelly", "models": [{"measure_device": "Shelly Plug S"}]}]}
    devices = MeasureDeviceCatalog(loader=lambda: library)
    manufacturers = ManufacturerCatalog(loader=lambda: library)

    devices.devices().clear()
    manufacturers.manufacturers().append("Unknown")

    assert devices.devices() == ["Shelly Plug S"]
    assert manufacturers.manufacturers() == ["Shelly"]


def test_resolve_manufacturer_name_uses_names_and_unambiguous_aliases() -> None:
    library = {
        "manufacturers": [
            {
                "name": "signify",
                "full_name": "Signify",
                "aliases": ["Signify Netherlands B.V.", "Philips Lighting"],
            },
            {"name": "antela", "full_name": "Antela", "aliases": ["Tuya"]},
            {"name": "generic tuya", "full_name": "Generic Tuya", "aliases": ["Tuya"]},
        ],
    }

    assert resolve_manufacturer_name(library, "SIGNIFY") == "Signify"
    assert resolve_manufacturer_name(library, "Signify Netherlands B.V.") == "Signify"
    assert resolve_manufacturer_name(library, "Tuya") == "Tuya"
    assert resolve_manufacturer_name(library, "New manufacturer") == "New manufacturer"


@pytest.mark.parametrize("library", [None, [], {}, {"manufacturers": {}}])
def test_extract_measure_devices_rejects_invalid_library_shapes(library: object) -> None:
    with pytest.raises(LibraryCatalogError):
        extract_measure_devices(library)


def test_catalog_translates_loader_failures_without_application_caching() -> None:
    calls = 0

    def load() -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"manufacturers": [{"models": [{"measure_device": "Shelly Plug S"}]}]}
        raise OSError("offline")

    catalog = MeasureDeviceCatalog(loader=load)

    assert catalog.devices() == ["Shelly Plug S"]
    with pytest.raises(LibraryCatalogError, match="Could not load measurement devices"):
        catalog.devices()
    assert calls == 2


def test_manufacturer_catalog_translates_loader_failures() -> None:
    catalog = ManufacturerCatalog(loader=lambda: (_ for _ in ()).throw(OSError("offline")))

    with pytest.raises(LibraryCatalogError, match="Could not load manufacturers"):
        catalog.manufacturers()


def test_device_specification_catalog_extracts_schema_fields() -> None:
    catalog = DeviceSpecificationCatalog(
        loader=lambda: {
            "properties": {
                "device_type": {"enum": ["generic_iot"]},
                "device_specs": {
                    "type": "object",
                    "properties": {"rated_power": {"type": "number", "description": "Rated power"}},
                },
            },
        },
    )

    assert [field.name for field in catalog.fields()["generic_iot"]] == ["rated_power"]
    catalog.fields()["generic_iot"].clear()
    assert [field.name for field in catalog.fields()["generic_iot"]] == ["rated_power"]


def test_manufacturer_resolution_ignores_invalid_names_and_aliases() -> None:
    catalog = ManufacturerCatalog(
        loader=lambda: {
            "manufacturers": [
                {"name": " ", "aliases": ["Invalid"]},
                {"name": 42, "aliases": ["Invalid"]},
                {"name": "Shelly", "aliases": "Not an alias list"},
                {"name": "Signify", "aliases": [None, 42, " ", " Philips ", "Shelly"]},
            ],
        },
    )

    assert catalog.canonical_name(" Philips ") == "Signify"
    assert catalog.canonical_name("Shelly") == "Shelly"
    assert catalog.canonical_name("Invalid") == "Invalid"
    assert catalog.canonical_name("Not an alias list") == "Not an alias list"
    assert catalog.canonical_name("  ") == ""


def test_manufacturer_resolution_preserves_loader_failure_cause() -> None:
    failure = OSError("Library unavailable")
    catalog = ManufacturerCatalog(loader=MagicMock(side_effect=failure))

    with pytest.raises(LibraryCatalogError, match="Could not load manufacturers") as error:
        catalog.canonical_name("Shelly")

    assert error.value.__cause__ is failure


@pytest.mark.parametrize("schema", [None, [], "invalid"])
def test_device_specification_catalog_rejects_non_object_schemas(schema: object) -> None:
    catalog = DeviceSpecificationCatalog(loader=lambda: schema)

    with pytest.raises(LibraryCatalogError, match="Could not load device specifications") as error:
        catalog.fields()

    assert isinstance(error.value.__cause__, TypeError)


def test_device_specification_catalog_preserves_loader_failure_cause() -> None:
    failure = OSError("Schema unavailable")
    catalog = DeviceSpecificationCatalog(loader=MagicMock(side_effect=failure))

    with pytest.raises(LibraryCatalogError, match="Could not load device specifications") as error:
        catalog.fields()

    assert error.value.__cause__ is failure


def test_default_manufacturer_catalog_reuses_library_until_cache_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.return_value = {"manufacturers": [{"name": "Shelly", "aliases": ["Shelly Europe"]}]}
    get = MagicMock(return_value=response)
    clock = MagicMock(return_value=100.0)
    monkeypatch.setattr(library_catalog.requests, "get", get)
    monkeypatch.setattr(library_catalog, "monotonic", clock)
    monkeypatch.setattr(
        library_catalog,
        "_cached_library",
        _CachedLoader(_load_published_library),
    )

    assert ManufacturerCatalog().manufacturers() == ["Shelly"]
    clock.return_value = 699.0
    assert ManufacturerCatalog().canonical_name("Shelly Europe") == "Shelly"
    get.assert_called_once_with(library_catalog.LIBRARY_ENDPOINT, timeout=15)

    response.json.return_value = {"manufacturers": [{"name": "IKEA"}]}
    clock.return_value = 700.0
    assert ManufacturerCatalog().manufacturers() == ["IKEA"]
    assert get.call_count == 2
    assert response.raise_for_status.call_count == 2


def test_default_schema_catalog_retries_after_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    failure = library_catalog.requests.HTTPError("Service unavailable")
    response.raise_for_status.side_effect = [failure, None]
    response.json.return_value = {"properties": {}}
    get = MagicMock(return_value=response)
    monkeypatch.setattr(library_catalog.requests, "get", get)
    monkeypatch.setattr(
        library_catalog,
        "_cached_model_schema",
        _CachedLoader(_load_published_model_schema),
    )

    with pytest.raises(LibraryCatalogError) as error:
        DeviceSpecificationCatalog().fields()

    assert error.value.__cause__ is failure
    response.json.assert_not_called()
    assert DeviceSpecificationCatalog().fields() == {}
    assert DeviceSpecificationCatalog().fields() == {}
    assert get.call_count == 2
    get.assert_called_with(library_catalog.MODEL_SCHEMA_ENDPOINT, timeout=15)
