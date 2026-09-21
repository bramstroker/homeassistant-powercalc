from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.ha_app.api import create_app
from measure.ha_app.library_catalog import (
    DeviceSpecificationCatalog,
    LibraryCatalogError,
    ManufacturerCatalog,
    MeasureDeviceCatalog,
    StandbyCatalog,
)
from measure.ha_app.routes.measurement import _power_meter_spec
from measure.home_assistant.client import HomeAssistantManager
from measure.powermeter.credentials import TapoCredentials
from measure.powermeter.diagnostics import PowerMeterDiagnostics
from measure.powermeter.powermeter import PowerMeter, PowerMeterDiagnosticSample
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, KasaPowerMeterSpec, ShellyPowerMeterSpec
from measure.tuning import MeasurementParameters
from measure.utils.version import measure_version
import pytest

from tests.ha_app.api_test_support import (
    AppClientFactory,
    FakeClient,
    payload,
)


def test_app_metadata_uses_the_runtime_measure_version(app_client: TestClient) -> None:
    assert app_client.app.version == measure_version()
    assert app_client.get("/openapi.json").json()["info"]["version"] == measure_version()
    assert app_client.get("/api/capabilities").json()["runtime_version"] == measure_version()


def test_standby_estimate_endpoint_uses_requested_connectivity_and_manufacturer(app_client: TestClient) -> None:
    app_client.app.state.context.standby_catalog = StandbyCatalog(
        loader=lambda: {
            "manufacturers": [
                {
                    "full_name": "Acme",
                    "models": [
                        {
                            "id": str(index),
                            "device_type": "light",
                            "standby_power": power,
                            "device_specs": {"connectivity": ["zigbee", "bluetooth"]},
                        }
                        for index, power in enumerate([0.2, 0.3, 0.6])
                    ],
                }
            ]
        }
    )
    response = app_client.get(
        "/api/library/standby-estimate", params={"manufacturer": "Acme", "connectivity": ["bluetooth", "zigbee"]}
    )
    assert response.status_code == 200
    assert response.json() == {"power_w": 0.3, "basis": "manufacturer", "profile_count": 3}
    assert app_client.get("/api/library/standby-estimate").json() == {
        "power_w": 0.4,
        "basis": "fallback",
        "profile_count": 0,
    }


def test_measure_device_catalog_uses_published_values_and_http_caching(app_client: TestClient) -> None:
    app_client.app.state.context.measure_device_catalog = MeasureDeviceCatalog(
        loader=lambda: {
            "manufacturers": [
                {"models": [{"measure_device": "Shelly Plug S"}, {"measure_device": "N/A"}]},
            ],
        },
    )

    response = app_client.get("/api/library/measure-devices")

    assert response.status_code == 200
    assert response.json() == {"devices": ["Shelly Plug S"]}
    assert response.headers["cache-control"] == "public, max-age=600"


def test_measure_device_catalog_failure_returns_service_unavailable(app_client: TestClient) -> None:
    app_client.app.state.context.measure_device_catalog = MeasureDeviceCatalog(
        loader=lambda: (_ for _ in ()).throw(OSError("offline")),
    )

    response = app_client.get("/api/library/measure-devices")

    assert response.status_code == 503
    assert response.json()["message"] == "Could not load measurement devices from the Powercalc library"


@pytest.mark.parametrize(
    "catalog_attribute,endpoint,method",
    [
        pytest.param("manufacturer_catalog", "manufacturers", "manufacturers", id="manufacturers"),
        pytest.param("device_specification_catalog", "device-specifications", "fields", id="device-specifications"),
    ],
)
def test_library_catalog_outage_returns_service_unavailable(
    app_client: TestClient, catalog_attribute: str, endpoint: str, method: str
) -> None:
    catalog = MagicMock()
    getattr(catalog, method).side_effect = LibraryCatalogError("Library unavailable")
    setattr(app_client.app.state.context, catalog_attribute, catalog)

    response = app_client.get(f"/api/library/{endpoint}")

    assert response.status_code == 503
    assert response.json()["message"] == "Library unavailable"
    assert "cache-control" not in response.headers


def test_manufacturer_catalog_uses_canonical_names_and_http_caching(app_client: TestClient) -> None:
    app_client.app.state.context.manufacturer_catalog = ManufacturerCatalog(
        loader=lambda: {
            "manufacturers": [
                {"name": "signify", "full_name": "Signify", "models": []},
                {"name": "ikea", "full_name": "IKEA", "models": []},
            ],
        },
    )

    response = app_client.get("/api/library/manufacturers")

    assert response.status_code == 200
    assert response.json() == {"manufacturers": ["IKEA", "Signify"]}
    assert response.headers["cache-control"] == "public, max-age=600"


def test_device_specification_catalog_exposes_schema_fields_by_device_type(
    app_client: TestClient,
) -> None:
    app_client.app.state.context.device_specification_catalog = DeviceSpecificationCatalog(
        loader=lambda: {
            "properties": {
                "device_type": {"enum": ["light"]},
                "device_specs": {
                    "type": "object",
                    "properties": {
                        "connectivity": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["zigbee", "wifi"]},
                            "description": "Communication protocols",
                        },
                    },
                },
            },
        },
    )

    response = app_client.get("/api/library/device-specifications")

    assert response.status_code == 200
    assert response.json() == {
        "device_types": {
            "light": [
                {
                    "name": "connectivity",
                    "label": "Connectivity",
                    "description": "Communication protocols",
                    "value_type": "string",
                    "collection": "array",
                    "options": ["zigbee", "wifi"],
                },
            ],
        },
    }
    assert response.headers["cache-control"] == "public, max-age=600"


def test_entity_manufacturer_normalizes_a_library_alias(app_client: TestClient) -> None:
    context = app_client.app.state.context
    context.home_assistant = FakeClient()
    context.manufacturer_catalog = ManufacturerCatalog(
        loader=lambda: {
            "manufacturers": [
                {
                    "name": "signify",
                    "full_name": "Signify",
                    "aliases": ["Signify Netherlands B.V."],
                },
            ],
        },
    )

    with patch.object(
        FakeClient,
        "get_device_registry",
        return_value=[
            {
                "id": "light-device",
                "manufacturer": "Signify Netherlands B.V.",
                "model": "Test light",
            },
        ],
    ):
        assert context.get_entity_manufacturers(["light.test"]) == {"light.test": "Signify"}


@pytest.mark.parametrize("manufacturer", [None, ""])
def test_entity_without_manufacturer_skips_library_lookup(app_client: TestClient, manufacturer: str | None) -> None:
    context = app_client.app.state.context
    context.home_assistant = FakeClient()
    catalog = MagicMock(spec=ManufacturerCatalog)
    context.manufacturer_catalog = catalog

    with patch.object(
        FakeClient,
        "get_device_registry",
        return_value=[{"id": "light-device", "manufacturer": manufacturer}],
    ):
        assert context.get_entity_manufacturers(["light.test", "light.missing"]) == {
            "light.test": None,
            "light.missing": None,
        }

    catalog.canonical_name.assert_not_called()


def test_manufacturer_lookup_failure_preserves_home_assistant_name(
    app_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    context = app_client.app.state.context
    context.home_assistant = FakeClient()
    catalog = MagicMock(spec=ManufacturerCatalog)
    catalog.canonical_name.side_effect = LibraryCatalogError("Library unavailable")
    context.manufacturer_catalog = catalog

    with patch.object(
        FakeClient,
        "get_device_registry",
        return_value=[{"id": "light-device", "manufacturer": "Acme Lighting"}],
    ):
        assert context.get_entity_manufacturers(["light.test"]) == {"light.test": "Acme Lighting"}

    assert "Could not normalize manufacturer Acme Lighting" in caplog.text


def test_index_is_not_cached(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    test_client = TestClient(
        create_app(
            data_root=tmp_path,
            hass_token="test-token",  # noqa: S106
            static_root=static_root,
            trusted_ingress_only=False,
        ),
        client=("127.0.0.1", 50000),
    )

    response = test_client.get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"


@pytest.mark.parametrize("token", [None, ""])
def test_app_requires_home_assistant_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str | None
) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="SUPERVISOR_TOKEN is required"):
        create_app(data_root=tmp_path, hass_token=token)


def test_app_accepts_supervisor_credentials_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-test-token")
    app = create_app(data_root=tmp_path, trusted_ingress_only=False)
    test_client = TestClient(app, client=("127.0.0.1", 50000))

    assert test_client.get("/health").json() == {"status": "ok"}


def test_frontend_assets_are_served_from_build_directory(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    assets = static_root / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_text("console.log('measure');", encoding="utf-8")
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        static_root=static_root,
        trusted_ingress_only=False,
    )
    test_client = TestClient(app, client=("127.0.0.1", 50000))

    response = test_client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('measure');"
    assert test_client.get("/assets/missing.js").status_code == 404


def test_backend_runs_without_frontend_build(tmp_path: Path) -> None:
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        static_root=tmp_path / "missing-build",
        trusted_ingress_only=False,
    )
    test_client = TestClient(app, client=("127.0.0.1", 50000))

    assert test_client.get("/health").status_code == 200
    assert test_client.get("/").status_code == 404
    assert test_client.get("/api/settings").status_code == 200


def test_capabilities_and_entity_filters(app_client_factory: AppClientFactory) -> None:
    test_client = app_client_factory()

    capabilities = test_client.get("/api/capabilities")
    powers = test_client.get("/api/entities?device_class=power")
    lights = test_client.get("/api/entities?domain=light")
    all_entities = test_client.get("/api/entities?all=true")

    assert capabilities.status_code == 200
    defaults = MeasurementParameters()
    assert capabilities.json()["defaults"] == {
        "sleep_time": defaults.sleep_time,
        "sample_count": defaults.sample_count,
        "sleep_time_sample": defaults.sleep_time_sample,
        "max_retries": defaults.max_retries,
        "max_nudges": defaults.max_nudges,
        "bri_bri_steps": defaults.bri_bri_steps,
        "ct_bri_steps": defaults.ct_bri_steps,
        "ct_mired_steps": defaults.ct_mired_steps,
        "hs_bri_steps": defaults.hs_bri_steps,
        "hs_hue_steps": defaults.hs_hue_steps,
        "hs_sat_steps": defaults.hs_sat_steps,
        "min_brightness": defaults.min_brightness,
        "min_sat": defaults.min_sat,
        "max_sat": defaults.max_sat,
        "min_hue": defaults.min_hue,
        "max_hue": defaults.max_hue,
        "sleep_initial": defaults.sleep_initial,
        "sleep_standby": defaults.sleep_standby,
        "effect_bri_steps": defaults.effect_bri_steps,
        "measure_time_effect": defaults.measure_time_effect,
        "measure_time_effect_min": defaults.measure_time_effect_min,
    }
    assert capabilities.json()["limits"]["ct_bri_steps"] == {"min": 1, "max": 10}
    assert capabilities.json()["limits"]["min_sat"] == {"min": 1, "max": 255}
    assert capabilities.json()["developer_mode"] is False
    assert app_client_factory(developer_mode=True).get("/api/capabilities").json()["developer_mode"] is True
    assert [item["entity_id"] for item in powers.json()] == ["sensor.test_power"]
    assert all_entities.status_code == 200
    temperature = next(item for item in all_entities.json() if item["entity_id"] == "sensor.temperature")
    assert temperature["domain"] == "sensor"
    assert temperature["device_class"] is None
    assert test_client.get("/api/entities?all=true&domain=vacuum").status_code == 400
    assert powers.json()[0]["device_id"] == "meter-device"
    assert powers.json()[0]["model_id"] == "PM-001"
    assert powers.json()[0]["related_voltage_entity_id"] == "sensor.test_voltage"
    assert test_client.get("/api/entities?kind=power").status_code == 400
    assert "light.switch_like" not in {item["entity_id"] for item in lights.json()}
    assert lights.json()[0]["supported_modes"] == ["brightness", "color_temp", "hs", "effect"]
    assert lights.json()[0]["model_id"] == "Hue White Ambiance"
    assert lights.json()[0]["min_mired"] == 153
    assert lights.json()[0]["max_mired"] == 454

    for domain, expected in (("fan", "fan.test"), ("media_player", "media_player.test"), ("vacuum", "vacuum.test")):
        response = test_client.get(f"/api/entities?domain={domain}")
        assert response.status_code == 200, domain
        assert [item["entity_id"] for item in response.json()] == [expected]


def test_entity_catalog_categorizes_one_fresh_snapshot(app_client: TestClient) -> None:
    home_assistant = app_client.app.state.context.home_assistant

    response = app_client.get("/api/entity-catalog")

    assert response.status_code == 200
    assert response.json()["home_assistant_ready"] is True
    assert home_assistant.entity_data_calls == 1
    assert [item["entity_id"] for item in response.json()["lights"]] == ["light.test"]
    assert [item["entity_id"] for item in response.json()["powers"]] == ["sensor.test_power"]
    assert [item["entity_id"] for item in response.json()["voltages"]] == ["sensor.test_voltage"]

    assert app_client.get("/api/entity-catalog").status_code == 200
    assert home_assistant.entity_data_calls == 2


def test_entity_catalog_waits_for_home_assistant_startup(app_client: TestClient) -> None:
    home_assistant = app_client.app.state.context.home_assistant

    with patch.object(home_assistant, "get_config", return_value={"state": "STARTING"}):
        response = app_client.get("/api/entity-catalog")

    assert response.status_code == 200
    assert response.json() == {
        "home_assistant_ready": False,
        "lights": [],
        "powers": [],
        "voltages": [],
    }
    assert home_assistant.entity_data_calls == 0


def test_entity_integration_is_resolved_and_stays_optional(app_client: TestClient) -> None:
    context = app_client.app.state.context

    assert context.get_entity_integrations(["light.test", "light.unknown"]) == {
        "light.test": "hue",
        "light.unknown": None,
    }

    context.home_assistant = MagicMock(spec=HomeAssistantManager)
    context.home_assistant.get_entity_data.side_effect = OSError("Home Assistant is unreachable")
    assert context.get_entity_integrations(["light.test"]) == {"light.test": None}


def test_entity_connectivity_uses_device_metadata_and_stays_optional(app_client: TestClient) -> None:
    context = app_client.app.state.context
    devices = [
        {"id": "light-device", "connections": [["mac", "00:17:88:01:02:03:04:05"]], "via_device_id": "bridge"},
        {"id": "bridge", "connections": [["mac", "00:11:22:33:44:55"]]},
    ]
    with patch.object(context.home_assistant, "get_device_registry", return_value=devices):
        assert context.get_entity_connectivity(["light.test", "light.missing"]) == {
            "light.test": "zigbee",
            "light.missing": None,
        }
    assert context.home_assistant.entity_data_calls == 1

    with patch.object(context.home_assistant, "get_device_registry", return_value=devices[1:]):
        assert context.get_entity_connectivity(["light.test"]) == {"light.test": None}
    with patch.object(context.home_assistant, "get_entity_data", side_effect=OSError("HA offline")):
        assert context.get_entity_connectivity(["light.test"]) == {"light.test": None}


@pytest.mark.parametrize("meter_type", ["hass", "shelly", "kasa"])
def test_saved_calibration_is_hidden_until_meter_settings_are_complete(app_client: TestClient, meter_type: str) -> None:
    storage = app_client.app.state.context.storage
    storage.save_dummy_load_calibration(
        DummyLoadCalibration(
            description="Resistive bulb",
            resistance=1322.5,
            calibrated_at="2026-09-18T10:00:00Z",
            power_meter_fingerprint=power_meter_fingerprint(DummyPowerMeterSpec()),
        )
    )
    assert app_client.put("/api/settings", json={"power_meter": meter_type}).status_code == 200

    response = app_client.get("/api/dummy-load/calibration")

    assert response.status_code == 200
    assert response.json() is None
    assert storage.load_dummy_load_calibration() is not None


def test_saved_calibration_matches_network_meter_without_home_assistant_lookup(
    app_client: TestClient,
) -> None:
    context = app_client.app.state.context
    spec = ShellyPowerMeterSpec(device_ip="192.168.1.10")
    calibration = DummyLoadCalibration(
        description="Resistive bulb",
        resistance=1322.5,
        calibrated_at="2026-09-18T10:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(spec),
    )
    context.storage.save_dummy_load_calibration(calibration)
    assert (
        app_client.put("/api/settings", json={"power_meter": "shelly", "shelly_ip": spec.device_ip}).status_code == 200
    )
    with patch.object(context.home_assistant, "get_entity_data", side_effect=AssertionError("HA lookup not needed")):
        response = app_client.get("/api/dummy-load/calibration")

    assert response.status_code == 200
    assert response.json() == calibration.model_dump(mode="json")


def test_calibration_endpoint_without_saved_calibration_returns_none(app_client: TestClient) -> None:
    response = app_client.get("/api/dummy-load/calibration")

    assert response.status_code == 200
    assert response.json() is None


def test_dummy_load_calibration_is_returned_only_for_the_configured_meter(app_client: TestClient) -> None:
    settings = {
        "default_power_entity_id": "sensor.test_power",
        "default_measure_device": "Test meter",
        "power_meter": "hass",
    }
    assert app_client.put("/api/settings", json=settings).status_code == 200
    calibration = DummyLoadCalibration(
        description="40 W incandescent bulb",
        resistance=1322.5,
        calibrated_at="2026-07-16T12:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(
            HassPowerMeterSpec(
                entity_id="sensor.test_power",
                voltage_entity_id="sensor.test_voltage",
            ),
        ),
    )
    app_client.app.state.context.storage.save_dummy_load_calibration(calibration)

    response = app_client.get("/api/dummy-load/calibration")

    assert response.status_code == 200
    assert response.json()["resistance"] == pytest.approx(1322.5)

    settings["default_power_entity_id"] = "sensor.other_power"
    assert app_client.put("/api/settings", json=settings).status_code == 200
    assert app_client.get("/api/dummy-load/calibration").json() is None


def test_dummy_load_preflight_requires_voltage_and_includes_calibration_time(
    app_client: TestClient,
) -> None:
    request = payload() | {
        "dummy_load": {
            "mode": "calibrate",
            "description": "40 W incandescent bulb",
        },
    }

    response = app_client.post("/api/preflight", json=request)

    assert response.status_code == 200
    assert response.json()["estimated_duration_seconds"] >= 600
    assert response.json()["light_load_probe"] is None
    app_client.app.state.context.light_load_probe.evaluate.assert_not_called()
    assert any("at least 10 minutes" in warning for warning in response.json()["warnings"])

    request["power_meter"] = {
        "type": "hass",
        "entity_id": "sensor.test_power",
        "voltage_entity_id": None,
    }
    response = app_client.post("/api/preflight", json=request)
    assert response.status_code == 422
    assert "voltage sensor is required" in response.json()["message"]


def test_charging_preflight_returns_discovered_battery_sensor(app_client: TestClient) -> None:
    response = app_client.post(
        "/api/preflight",
        json={
            "measure_type": "charging",
            "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
            "controller": {"type": "hass", "entity_id": "vacuum.test"},
            "charging_device_type": "vacuum_robot",
        },
    )

    assert response.status_code == 200
    assert response.json()["battery_level_entity_id"] == "sensor.vacuum_battery"
    assert response.json()["battery_level_attribute"] is None


def test_shelly_dummy_load_preflight_builds_and_probes_the_meter_once(app_client: TestClient) -> None:
    context = app_client.app.state.context
    meter = MagicMock(spec=PowerMeter)
    meter.has_voltage_support.return_value = True
    meter.diagnostic_sample.return_value = PowerMeterDiagnosticSample(power=4.2, raw_value="4.2", reported_at=100)
    builder = MagicMock(return_value=meter)
    context.power_meter_diagnostics = PowerMeterDiagnostics(builder, duration=0)
    request = payload() | {
        "power_meter": {"type": "shelly", "device_ip": "192.0.2.1"},
        "dummy_load": {"mode": "calibrate", "description": "40 W incandescent bulb"},
    }

    with patch.object(context, "create_power_meter", builder):
        response = app_client.post("/api/preflight", json=request)

    assert response.status_code == 200
    builder.assert_called_once()
    meter.has_voltage_support.assert_called_once_with()
    meter.diagnostic_sample.assert_called_once_with()


def test_kasa_settings_round_trip_into_a_power_meter_spec(app_client: TestClient) -> None:

    stored = app_client.put("/api/settings", json={"power_meter": "kasa", "kasa_ip": "192.0.2.30"})

    assert stored.status_code == 200
    assert app_client.get("/api/settings").json()["kasa_ip"] == "192.0.2.30"
    settings = app_client.app.state.context.storage.load_settings()
    assert _power_meter_spec(settings) == KasaPowerMeterSpec(device_ip="192.0.2.30")


def test_kasa_preflight_builds_and_probes_the_meter(app_client: TestClient) -> None:
    context = app_client.app.state.context
    meter = MagicMock(spec=PowerMeter)
    meter.has_voltage_support.return_value = True
    meter.diagnostic_sample.return_value = PowerMeterDiagnosticSample(power=4.2, raw_value="4.2", reported_at=100)
    builder = MagicMock(return_value=meter)
    context.power_meter_diagnostics = PowerMeterDiagnostics(builder, duration=0)
    request = payload() | {"power_meter": {"type": "kasa", "device_ip": "192.0.2.1"}}

    with patch.object(context, "create_power_meter", builder):
        response = app_client.post("/api/preflight", json=request)

    assert response.status_code == 200
    builder.assert_called_once()
    assert builder.call_args.args[0] == KasaPowerMeterSpec(device_ip="192.0.2.1")


def test_tapo_credentials_are_kept_out_of_preferences_and_are_available_to_the_kasa_meter(
    app_client: TestClient, tmp_path: Path
) -> None:
    payload = {
        "power_meter": "kasa",
        "kasa_ip": "192.0.2.31",
        "tapo_username": "user@example.com",
        "tapo_password": "account-password",
    }

    stored = app_client.put("/api/settings", json=payload)

    assert stored.status_code == 200
    assert stored.json()["tapo_credentials_configured"] is True
    assert "tapo_username" not in stored.json()
    assert "tapo_password" not in stored.json()
    assert "account-password" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert (tmp_path / "tapo_credentials.json").stat().st_mode & 0o777 == 0o600
    settings = app_client.app.state.context.storage.load_settings()
    assert _power_meter_spec(settings) == KasaPowerMeterSpec(device_ip="192.0.2.31")
    credentials = app_client.app.state.context.get_tapo_credentials()
    assert isinstance(credentials, TapoCredentials)
    assert credentials.username == payload["tapo_username"]
    assert credentials.password == payload["tapo_password"]

    cleared = app_client.put(
        "/api/settings",
        json=payload | {"tapo_username": None, "tapo_password": None, "clear_tapo_credentials": True},
    )
    assert cleared.json()["tapo_credentials_configured"] is False
    assert not (tmp_path / "tapo_credentials.json").exists()


def test_app_closes_home_assistant_manager_at_shutdown(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106
    home_assistant = MagicMock(spec=HomeAssistantManager)
    app.state.context.home_assistant = home_assistant

    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        assert test_client.get("/api/capabilities").status_code == 200

    home_assistant.close.assert_called_once_with()


def test_power_meter_test_endpoint(app_client: TestClient) -> None:

    dummy = app_client.post("/api/settings/test-power-meter", json={"power_meter": "dummy"})
    assert dummy.status_code == 200
    assert dummy.json()["success"] is True
    assert dummy.json()["status"] == "unsupported"
    assert dummy.json()["supports_voltage"] is True

    shelly = app_client.post("/api/settings/test-power-meter", json={"power_meter": "shelly", "shelly_ip": None})
    assert shelly.json()["success"] is False
    assert shelly.json()["message"] == "Enter the Shelly IP address first"

    kasa = app_client.post("/api/settings/test-power-meter", json={"power_meter": "kasa", "kasa_ip": None})
    assert kasa.json()["success"] is False
    assert kasa.json()["message"] == "Enter the Kasa IP address first"

    hass = app_client.post(
        "/api/settings/test-power-meter",
        json={"power_meter": "hass", "default_power_entity_id": None},
    )
    assert hass.json()["success"] is False
    assert "power sensor" in hass.json()["message"].lower()

    validated = app_client.post(
        "/api/settings/test-power-meter",
        json={"power_meter": "hass", "default_power_entity_id": "sensor.test_power"},
    )
    assert validated.json()["success"] is True
    assert validated.json()["supports_voltage"] is False
    assert validated.json()["precision_decimals"] == 1
    assert validated.json()["update_interval_status"] == "poor"


@pytest.mark.parametrize(
    "credential_settings,expected_username",
    [
        ({"tapo_username": "entered@example.com", "tapo_password": "entered-password"}, "entered@example.com"),
        ({}, "saved@example.com"),
        ({"clear_tapo_credentials": True}, None),
    ],
)
def test_power_meter_test_uses_selected_tapo_credentials_without_saving(
    app_client: TestClient,
    credential_settings: dict[str, object],
    expected_username: str | None,
) -> None:
    storage = app_client.app.state.context.storage
    saved = TapoCredentials(username="saved@example.com", password="saved-password")  # noqa: S106
    storage.save_tapo_credentials(saved)
    meter = MagicMock(spec=PowerMeter)
    meter.has_voltage_support.return_value = False
    meter.diagnostic_sample.return_value = PowerMeterDiagnosticSample(power=5.1, raw_value="5.1", reported_at=1)

    with patch("measure.powermeter.kasa.KasaPowerMeter", return_value=meter) as create_meter:
        response = app_client.post(
            "/api/settings/test-power-meter",
            json={"power_meter": "kasa", "kasa_ip": "192.0.2.31"} | credential_settings,
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    create_meter.assert_called_once()
    credentials = create_meter.call_args.kwargs["credentials"]
    if expected_username is None:
        assert credentials is None
    else:
        assert isinstance(credentials, TapoCredentials)
        assert credentials.username == expected_username
        assert credentials.password == credential_settings.get("tapo_password", saved.password)
    assert storage.load_tapo_credentials() == saved


def test_shelly_discovery_endpoint(app_client: TestClient) -> None:

    response = app_client.get("/api/power-meters/shelly")

    assert response.status_code == 200
    assert response.json() == {"devices": [], "available": True, "message": None}


@pytest.mark.parametrize("saved", [False, True])
def test_calibration_match_uses_requested_meter_not_settings(app_client: TestClient, saved: bool) -> None:
    meter = HassPowerMeterSpec(entity_id="sensor.session_power", voltage_entity_id="sensor.session_voltage")
    calibration = DummyLoadCalibration(
        description="Warm bulb",
        resistance=1322.5,
        calibrated_at="2026-09-20T12:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(meter),
    )
    if saved:
        app_client.app.state.context.storage.save_dummy_load_calibration(calibration)
    assert app_client.get("/api/dummy-load/calibration").json() is None
    response = app_client.post("/api/dummy-load/calibration/match", json=meter.model_dump(mode="json"))
    assert response.status_code == 200
    assert response.json() == (calibration.model_dump(mode="json") if saved else None)
    other_meter = meter.model_copy(update={"voltage_entity_id": "sensor.other_voltage"})
    assert app_client.post("/api/dummy-load/calibration/match", json=other_meter.model_dump(mode="json")).json() is None


@pytest.mark.parametrize("endpoint", ["preflight", "sessions"])
@pytest.mark.parametrize("mismatch", ["missing", "meter", "description", "resistance", None])
def test_new_measurement_reuse_requires_matching_saved_calibration(
    app_client: TestClient,
    endpoint: str,
    mismatch: str | None,
) -> None:
    request = payload()
    calibration = DummyLoadCalibration(
        description="Warm bulb",
        resistance=1322.5,
        calibrated_at="2026-09-20T12:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(
            HassPowerMeterSpec(
                entity_id="sensor.test_power",
                voltage_entity_id="sensor.test_voltage",
            )
        ),
    )
    request["dummy_load"] = {
        "mode": "reuse",
        "description": calibration.description,
        "resistance": calibration.resistance,
    }
    if mismatch == "meter":
        calibration = calibration.model_copy(update={"power_meter_fingerprint": "other"})
    elif mismatch == "description":
        calibration = calibration.model_copy(update={"description": "Other bulb"})
    elif mismatch == "resistance":
        calibration = calibration.model_copy(update={"resistance": 2000})
    if mismatch != "missing":
        app_client.app.state.context.storage.save_dummy_load_calibration(calibration)
    response = app_client.post(f"/api/{endpoint}", json=request)
    if mismatch is None:
        assert response.status_code == (200 if endpoint == "preflight" else 201)
    else:
        assert response.status_code == 422
        assert "No compatible saved dummy-load calibration" in response.json()["message"]
