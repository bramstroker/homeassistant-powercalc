from measure.ha_app.library_catalog import LibraryCatalogError, MeasureDeviceCatalog, extract_measure_devices
import pytest


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
