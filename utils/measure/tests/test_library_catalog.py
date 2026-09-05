from measure.ha_app import library_catalog
from measure.ha_app.library_catalog import (
    FULL_LIBRARY_ENDPOINT,
    DeviceSpecificationCatalog,
    LibraryCatalogError,
    ManufacturerCatalog,
    MeasureDeviceCatalog,
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

    assert MeasureDeviceCatalog().devices() == ("Shelly Plug S",)
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
                ],
            },
            {"models": [{"measure_device": "See linked profile"}]},
            {"models": "invalid"},
            "invalid",
        ],
    }

    assert extract_measure_devices(library) == ("Shelly Plug S", "TP-Link Kasa KP115")


def test_extract_manufacturers_prefers_full_names_and_removes_case_duplicates() -> None:
    library = {
        "manufacturers": [
            {"name": "signify", "full_name": "Signify", "models": []},
            {"name": "SIGNIFY", "models": []},
            {"name": " IKEA ", "models": []},
            {"name": "", "models": []},
            "invalid",
        ],
    }

    assert extract_manufacturers(library) == ("IKEA", "Signify")


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

    assert catalog.devices() == ("Shelly Plug S",)
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
