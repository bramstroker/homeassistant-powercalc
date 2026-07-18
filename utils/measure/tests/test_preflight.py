from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from measure.controller.charging.const import BatteryLevelSourceType
from measure.controller.charging.spec import HassChargingControllerSpec
from measure.controller.fan.spec import HassFanControllerSpec
from measure.controller.light.const import LutMode
from measure.controller.light.spec import DummyLightControllerSpec, HassLightControllerSpec
from measure.controller.media.spec import HassMediaControllerSpec
from measure.ha_app.preflight import ActiveSessionError, EntityRecord, MeasurementPreflight, PreflightError
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, ShellyPowerMeterSpec
from measure.request import (
    AverageMeasurementRequest,
    ChargingMeasurementRequest,
    DummyLoadCalibrationRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    SpeakerMeasurementRequest,
)
import pytest


@dataclass
class Entity(EntityRecord):
    entity_id: str
    supported_modes: list[LutMode] | None = None
    effect_list: list[str] | None = None
    min_mired: int | None = None
    max_mired: int | None = None
    state: str = "available"
    attribute_names: list[str] = field(default_factory=list)


def preflight(
    entities: dict[tuple[str | None, str | None], list[Entity]],
    *,
    active: bool = False,
    writable: bool = True,
    voltage_supported: bool | None = True,
    developer_mode: bool = True,
) -> MeasurementPreflight:
    def verify() -> None:
        if not writable:
            raise OSError("read only")

    return MeasurementPreflight(
        has_active_session=lambda: active,
        verify_storage=verify,
        load_entities=lambda domain, device_class: entities.get((domain, device_class), []),
        diagnose_power_meter=lambda _: PowerMeterDiagnostic(
            success=voltage_supported is not None,
            status=DiagnosticStatus.GOOD if voltage_supported is not None else DiagnosticStatus.POOR,
            precision_status=DiagnosticStatus.UNSUPPORTED,
            update_interval_status=DiagnosticStatus.UNSUPPORTED,
            supports_voltage=voltage_supported,
            message="Could not inspect voltage capability" if voltage_supported is None else None,
        ),
        developer_mode=developer_mode,
    )


def base_entities() -> dict[tuple[str | None, str | None], list[Entity]]:
    return {
        (None, "power"): [Entity("sensor.power")],
        (None, "voltage"): [Entity("sensor.voltage")],
        ("light", None): [Entity("light.test", [LutMode.BRIGHTNESS])],
        ("media_player", None): [Entity("media_player.test")],
        ("fan", None): [Entity("fan.test")],
        ("vacuum", None): [Entity("vacuum.test", attribute_names=["battery_level"])],
        ("lawn_mower", None): [Entity("lawn_mower.test", attribute_names=["battery_level"])],
        ("sensor", None): [Entity("sensor.battery", state="75")],
    }


@pytest.mark.parametrize(
    "payload",
    [
        AverageMeasurementRequest(power_meter=HassPowerMeterSpec(entity_id="sensor.power")),
        SpeakerMeasurementRequest(
            power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
            controller=HassMediaControllerSpec(entity_id="media_player.test"),
        ),
        FanMeasurementRequest(
            power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
            controller=HassFanControllerSpec(entity_id="fan.test"),
        ),
        ChargingMeasurementRequest(
            power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
            controller=HassChargingControllerSpec(entity_id="vacuum.test"),
            charging_device_type="vacuum_robot",
        ),
    ],
)
def test_preflight_validates_runtime_dependencies_for_every_non_light_kind(payload: Any) -> None:  # noqa: ANN401
    assert preflight(base_entities()).validate(payload).warnings == ()


def test_preflight_rejects_missing_hass_power_entity_for_non_light_kind() -> None:
    request = AverageMeasurementRequest(power_meter=HassPowerMeterSpec(entity_id="sensor.missing"))
    checker = preflight(base_entities())

    with pytest.raises(PreflightError, match="power entity"):
        checker.validate(request)


def test_preflight_requires_voltage_sensor_for_dummy_load() -> None:
    request = AverageMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )

    checker = preflight(base_entities())
    with pytest.raises(PreflightError, match="voltage sensor is required"):
        checker.validate(request)


def test_preflight_rejects_power_meter_without_dummy_load_voltage_support() -> None:
    request = AverageMeasurementRequest(
        power_meter=ShellyPowerMeterSpec(device_ip="192.168.1.50"),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )

    checker = preflight(base_entities(), voltage_supported=False)
    with pytest.raises(PreflightError, match="does not support voltage"):
        checker.validate(request)


def test_preflight_reports_unknown_dummy_load_voltage_capability() -> None:
    request = AverageMeasurementRequest(
        power_meter=ShellyPowerMeterSpec(device_ip="192.168.1.50"),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )

    with pytest.raises(PreflightError, match="Could not inspect voltage capability"):
        preflight(base_entities(), voltage_supported=None).validate(request)


def test_dummy_load_sampling_failure_does_not_mask_controller_validation() -> None:
    diagnostic = PowerMeterDiagnostic(
        success=False,
        supports_voltage=True,
        status=DiagnosticStatus.POOR,
        precision_status=DiagnosticStatus.UNSUPPORTED,
        update_interval_status=DiagnosticStatus.UNSUPPORTED,
        message="Could not read power",
    )
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda domain, device_class: base_entities().get((domain, device_class), []),
        diagnose_power_meter=lambda _: diagnostic,
        developer_mode=True,
    )
    request = SpeakerMeasurementRequest(
        power_meter=ShellyPowerMeterSpec(device_ip="192.168.1.50"),
        controller=HassMediaControllerSpec(entity_id="media_player.missing"),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )

    with pytest.raises(PreflightError, match="media player"):
        checker.validate(request)


def test_preflight_includes_minimum_dummy_load_calibration_duration() -> None:
    request = AverageMeasurementRequest(
        power_meter=HassPowerMeterSpec(
            entity_id="sensor.power",
            voltage_entity_id="sensor.voltage",
        ),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )

    result = preflight(base_entities()).validate(request)

    assert result.estimated_duration_seconds == 600
    assert "at least 10 minutes" in result.warnings[0]


@pytest.mark.parametrize(
    ("measurement", "message"),
    [
        (
            LightMeasurementRequest(
                model_id="LCT010",
                product_name="Test light",
                measure_device="Test meter",
                power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
                controller=HassLightControllerSpec(entity_id="light.missing"),
            ),
            "light entity",
        ),
        (
            SpeakerMeasurementRequest(
                power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
                controller=HassMediaControllerSpec(entity_id="media_player.missing"),
            ),
            "media player",
        ),
        (
            FanMeasurementRequest(
                power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
                controller=HassFanControllerSpec(entity_id="fan.missing"),
            ),
            "fan",
        ),
        (
            ChargingMeasurementRequest(
                power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
                controller=HassChargingControllerSpec(entity_id="lawn_mower.missing"),
                charging_device_type="vacuum_robot",
            ),
            "does not match",
        ),
    ],
)
def test_preflight_requires_ha_device_entities(measurement: Any, message: str) -> None:  # noqa: ANN401
    checker = preflight(base_entities())

    with pytest.raises(PreflightError, match=message):
        checker.validate(measurement)


def test_preflight_rejects_charging_type_entity_domain_mismatch() -> None:
    request = ChargingMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassChargingControllerSpec(entity_id="vacuum.test"),
        charging_device_type="lawn_mower_robot",
    )
    checker = preflight(base_entities())

    with pytest.raises(PreflightError, match="does not match"):
        checker.validate(request)


def test_preflight_rejects_missing_charging_battery_attribute() -> None:
    request = ChargingMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassChargingControllerSpec(entity_id="vacuum.test", battery_level_attribute="charge_percent"),
        charging_device_type="vacuum_robot",
    )

    with pytest.raises(PreflightError, match=r"charge_percent.*not available"):
        preflight(base_entities()).validate(request)


@pytest.mark.parametrize(
    ("battery_entity", "entities", "message"),
    [
        ("sensor.missing", base_entities(), "battery level sensor is unavailable"),
        (
            "sensor.battery",
            base_entities() | {("sensor", None): [Entity("sensor.battery", state="unknown")]},
            "numeric percentage",
        ),
    ],
)
def test_preflight_rejects_invalid_charging_battery_sensor(
    battery_entity: str,
    entities: dict[tuple[str | None, str | None], list[Entity]],
    message: str,
) -> None:
    request = ChargingMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassChargingControllerSpec(
            entity_id="vacuum.test",
            battery_level_source_type=BatteryLevelSourceType.ENTITY,
            battery_level_entity_id=battery_entity,
        ),
        charging_device_type="vacuum_robot",
    )

    with pytest.raises(PreflightError, match=message):
        preflight(entities).validate(request)


def test_light_preflight_accepts_dummy_controller_without_entity_checks() -> None:
    request = LightMeasurementRequest(
        model_id="dummy",
        product_name="Virtual light",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=DummyLightControllerSpec(),
        modes={LutMode.BRIGHTNESS},
        parameters={"sleep_time": 0.5, "sample_count": 2},
    )

    result = preflight(base_entities()).validate(request)

    assert result.supported_modes == (LutMode.BRIGHTNESS,)
    assert result.estimated_variations == 255
    assert result.estimated_duration_seconds is not None


def test_light_preflight_returns_supported_modes_and_estimate() -> None:
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(
            entity_id="sensor.power",
            voltage_entity_id="sensor.voltage",
        ),
        controller=HassLightControllerSpec(entity_id="light.test"),
        modes={LutMode.BRIGHTNESS},
        parameters={"sleep_time": 0.5, "sample_count": 2},
    )

    result = preflight(base_entities()).validate(request)

    assert result.supported_modes == (LutMode.BRIGHTNESS,)
    assert result.estimated_variations == 255
    assert result.estimated_duration_seconds == 782


def test_light_preflight_uses_device_color_temperature_range() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity(
            "light.test",
            [LutMode.COLOR_TEMP],
            min_mired=200,
            max_mired=300,
        ),
    ]
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassLightControllerSpec(entity_id="light.test"),
        modes={LutMode.COLOR_TEMP},
        parameters={"ct_bri_steps": 10, "ct_mired_steps": 10},
    )

    result = preflight(entities).validate(request)

    assert result.estimated_variations == 297


def test_light_preflight_uses_default_color_temperature_resolution() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity(
            "light.test",
            [LutMode.COLOR_TEMP],
            min_mired=150,
            max_mired=500,
        ),
    ]
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassLightControllerSpec(entity_id="light.test"),
        modes={LutMode.COLOR_TEMP},
    )

    result = preflight(entities).validate(request)

    assert result.estimated_variations == 1_872


def test_hs_preflight_uses_default_native_resolution() -> None:
    entities = base_entities()
    entities[("light", None)] = [Entity("light.test", [LutMode.HS])]
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassLightControllerSpec(entity_id="light.test"),
        modes={LutMode.HS},
    )

    result = preflight(entities).validate(request)

    assert result.estimated_variations == 2_025


def test_preflight_reports_active_session_before_external_checks() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    checker = preflight({}, active=True)

    with pytest.raises(ActiveSessionError):
        checker.validate(request)


def test_preflight_reports_unwritable_storage() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())
    checker = preflight({}, writable=False)

    with pytest.raises(PreflightError, match="not writable"):
        checker.validate(request)


def test_non_hass_power_meter_does_not_require_power_entity() -> None:
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())

    result = preflight({}).validate(request)

    assert result.warnings == ()
