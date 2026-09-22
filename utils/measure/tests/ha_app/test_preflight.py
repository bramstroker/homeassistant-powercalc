from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock

from measure.controller.charging.spec import DummyChargingControllerSpec, HassChargingControllerSpec
from measure.controller.fan.spec import DummyFanControllerSpec, HassFanControllerSpec
from measure.controller.light.const import LutMode
from measure.controller.light.spec import (
    DummyLightControllerSpec,
    HassLightControllerSpec,
    HassMultiLightControllerSpec,
)
from measure.controller.media.spec import DummyMediaControllerSpec, HassMediaControllerSpec
from measure.ha_app.preflight import ActiveSessionError, EntityRecord, MeasurementPreflight, PreflightError
from measure.home_assistant.entities import DeviceClass
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, ShellyPowerMeterSpec
from measure.request import (
    AverageMeasurementRequest,
    ChargingMeasurementRequest,
    DummyLoadCalibrationRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    RecorderMeasurementRequest,
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
    device_id: str | None = None
    model_id: str | None = None
    member_entity_ids: list[str] = field(default_factory=list)
    domain: str = ""
    device_class: str | None = None
    disabled_by: str | None = None
    has_live_state: bool = True


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
        load_all_entities=lambda: list(
            {entity.entity_id: entity for group in entities.values() for entity in group}.values(),
        ),
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


def test_preflight_accepts_request_without_meter_diagnostics() -> None:
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda _domain, _device_class: [],
    )

    result = checker.validate(AverageMeasurementRequest(power_meter=ShellyPowerMeterSpec(device_ip="192.0.2.1")))

    assert result.power_meter_diagnostic is None
    assert result.warnings == []


def test_preflight_rejects_dummy_controller_outside_developer_mode() -> None:
    request = SpeakerMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"), controller=DummyMediaControllerSpec()
    )

    with pytest.raises(PreflightError, match="Dummy controllers require developer mode"):
        preflight(base_entities(), developer_mode=False).validate(request)


def test_preflight_accepts_dummy_charging_controller_in_developer_mode() -> None:
    request = ChargingMeasurementRequest(
        power_meter=DummyPowerMeterSpec(), controller=DummyChargingControllerSpec(), charging_device_type="vacuum_robot"
    )

    result = preflight({}).validate(request)

    assert result.battery_level_entity_id is None
    assert result.battery_level_attribute is None


@pytest.mark.parametrize(
    "measurement_request",
    [
        SpeakerMeasurementRequest(power_meter=DummyPowerMeterSpec(), controller=DummyMediaControllerSpec()),
        FanMeasurementRequest(power_meter=DummyPowerMeterSpec(), controller=DummyFanControllerSpec()),
    ],
)
def test_developer_preflight_accepts_synthetic_controllers_without_home_assistant_entities(
    measurement_request: SpeakerMeasurementRequest | FanMeasurementRequest,
) -> None:
    checker = preflight({}, developer_mode=True)

    result = checker.validate(measurement_request)

    assert result.warnings == []
    assert result.power_meter_diagnostic is not None
    assert result.power_meter_diagnostic.success is True

    real_meter_request = measurement_request.model_copy(
        update={"power_meter": ShellyPowerMeterSpec(device_ip="192.0.2.1")}
    )
    with pytest.raises(PreflightError, match="Dummy controllers require developer mode"):
        preflight({}, developer_mode=False).validate(real_meter_request)


def test_dummy_load_requires_known_voltage_capability_even_after_successful_reading() -> None:
    diagnostic = PowerMeterDiagnostic(
        success=True,
        status=DiagnosticStatus.GOOD,
        precision_status=DiagnosticStatus.UNSUPPORTED,
        update_interval_status=DiagnosticStatus.UNSUPPORTED,
        supports_voltage=None,
    )
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda _domain, _device_class: [],
        diagnose_power_meter=lambda _: diagnostic,
    )
    request = AverageMeasurementRequest(
        power_meter=ShellyPowerMeterSpec(device_ip="192.0.2.1"),
        dummy_load=DummyLoadCalibrationRequest(description="Resistive bulb"),
    )

    with pytest.raises(PreflightError, match="Could not determine whether the selected power meter supports voltage"):
        checker.validate(request)


def test_preflight_rejects_unadvertised_light_mode() -> None:
    request = LightMeasurementRequest(
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassLightControllerSpec(entity_id="light.test"),
        modes={LutMode.COLOR_TEMP},
    )

    with pytest.raises(PreflightError, match="does not advertise every requested mode"):
        preflight(base_entities()).validate(request)


def test_preflight_rejects_non_overlapping_color_temperature_ranges() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity("light.warm", [LutMode.COLOR_TEMP], min_mired=300, max_mired=400, model_id="same-model"),
        Entity("light.cool", [LutMode.COLOR_TEMP], min_mired=150, max_mired=250, model_id="same-model"),
    ]
    request = LightMeasurementRequest(
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassMultiLightControllerSpec(entity_ids=["light.warm", "light.cool"]),
        multiple_light_count=2,
        modes={LutMode.COLOR_TEMP},
    )

    with pytest.raises(PreflightError, match="do not share a color temperature range"):
        preflight(entities).validate(request)


def test_preflight_rejects_unavailable_voltage_sensor() -> None:
    request = AverageMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power", voltage_entity_id="sensor.missing"),
    )

    with pytest.raises(PreflightError, match="voltage entity is unavailable"):
        preflight(base_entities()).validate(request)


@pytest.mark.parametrize("message", [None, "Meter did not respond"])
def test_preflight_reports_meter_diagnostic_failure(message: str | None) -> None:
    diagnostic = PowerMeterDiagnostic(
        success=False,
        status=DiagnosticStatus.POOR,
        precision_status=DiagnosticStatus.UNSUPPORTED,
        update_interval_status=DiagnosticStatus.UNSUPPORTED,
        message=message,
    )
    diagnose = Mock(return_value=diagnostic)
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda _domain, _device_class: [],
        diagnose_power_meter=diagnose,
    )
    request = AverageMeasurementRequest(power_meter=ShellyPowerMeterSpec(device_ip="192.0.2.1"))

    with pytest.raises(PreflightError, match=message or "Could not read from the power meter"):
        checker.validate(request)
    diagnose.assert_called_once_with(request.power_meter)


@pytest.mark.parametrize("status", [DiagnosticStatus.WARNING, DiagnosticStatus.POOR])
@pytest.mark.parametrize("with_dummy_load", [False, True])
def test_preflight_preserves_meter_warnings_without_repeating_diagnostics(
    status: DiagnosticStatus, with_dummy_load: bool
) -> None:
    diagnostic = PowerMeterDiagnostic(
        success=True,
        status=status,
        precision_status=status,
        update_interval_status=DiagnosticStatus.GOOD,
        supports_voltage=True,
        messages=["Meter precision is low"],
    )
    diagnose = Mock(return_value=diagnostic)
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda _domain, _device_class: [],
        diagnose_power_meter=diagnose,
    )
    request = AverageMeasurementRequest(
        power_meter=ShellyPowerMeterSpec(device_ip="192.0.2.1"),
        dummy_load=DummyLoadCalibrationRequest(description="Resistive bulb") if with_dummy_load else None,
    )

    result = checker.validate(request)

    assert result.power_meter_diagnostic == diagnostic
    assert result.warnings.count("Meter precision is low") == 1
    diagnose.assert_called_once_with(request.power_meter)


@pytest.mark.parametrize(
    "entity, message",
    [
        (Entity("sensor.disabled", disabled_by="integration"), "Selected recorder entity is disabled"),
        (Entity("sensor.disabled", has_live_state=False), "Selected recorder entity has no live state"),
    ],
)
def test_preflight_rejects_inactive_recorder_entity(entity: Entity, message: str) -> None:
    entities = base_entities()
    entities[("sensor", None)] = [entity]
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("sensor.disabled",),
    )
    validator = preflight(entities)
    with pytest.raises(PreflightError, match=message):
        validator.validate(request)


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
    assert preflight(base_entities()).validate(payload).warnings == []


def test_preflight_rejects_missing_hass_power_entity_for_non_light_kind() -> None:
    request = AverageMeasurementRequest(power_meter=HassPowerMeterSpec(entity_id="sensor.missing"))
    checker = preflight(base_entities())

    with pytest.raises(PreflightError, match="power entity"):
        checker.validate(request)


@pytest.mark.parametrize(
    "extra, message",
    [
        (Entity("sensor.extra", disabled_by="integration", domain="sensor"), "is disabled"),
        (Entity("sensor.extra", has_live_state=False, domain="sensor"), "has no live state"),
        (None, "does not exist"),
    ],
)
def test_preflight_warns_instead_of_failing_for_unusable_optional_recorder_entity(
    extra: Entity | None, message: str
) -> None:
    """A stored request must stay runnable when an additional entity goes away.

    The runner records such an entity as "unavailable", so record-more and resume would be
    permanently blocked if preflight rejected the whole request over it.
    """

    entities = base_entities()
    vacuum = Entity("vacuum.test", device_id="robot-device", domain="vacuum")
    battery = Entity(
        "sensor.robot_battery",
        state="42",
        device_id="robot-device",
        domain="sensor",
        device_class=DeviceClass.BATTERY,
    )
    entities[("vacuum", None)] = [vacuum]
    entities[(None, "battery")] = [battery]
    if extra is not None:
        entities[("sensor", None)] = [*entities[("sensor", None)], extra]
    request = RecorderMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id=vacuum.entity_id,
        battery_entity_id=battery.entity_id,
        additional_entity_ids=("sensor.extra",),
    )

    warnings = preflight(entities).validate(request).warnings

    assert len(warnings) == 1
    assert message in warnings[0]
    assert "recorded as unavailable" in warnings[0]


@pytest.mark.parametrize("field_name", ["vacuum_entity_id", "battery_entity_id"])
def test_preflight_still_rejects_an_unusable_required_vacuum_entity(field_name: str) -> None:
    entities = base_entities()
    vacuum = Entity("vacuum.test", device_id="robot-device", domain="vacuum")
    battery = Entity(
        "sensor.robot_battery",
        state="42",
        device_id="robot-device",
        domain="sensor",
        device_class=DeviceClass.BATTERY,
    )
    broken = vacuum if field_name == "vacuum_entity_id" else battery
    broken.disabled_by = "integration"
    entities[("vacuum", None)] = [vacuum]
    entities[(None, "battery")] = [battery]
    request = RecorderMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id=vacuum.entity_id,
        battery_entity_id=battery.entity_id,
    )

    with pytest.raises(PreflightError, match="Selected recorder entity is disabled"):
        preflight(entities).validate(request)


def test_preflight_accepts_vacuum_recorder_with_same_device_battery() -> None:
    entities = base_entities()
    vacuum = Entity("vacuum.test", device_id="robot-device", domain="vacuum")
    battery = Entity(
        "sensor.robot_battery",
        state="42",
        device_id="robot-device",
        domain="sensor",
        device_class=DeviceClass.BATTERY,
    )
    entities[("vacuum", None)] = [vacuum]
    entities[(None, "battery")] = [battery]
    request = RecorderMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id=vacuum.entity_id,
        battery_entity_id=battery.entity_id,
    )

    assert preflight(entities).validate(request).warnings == []


def test_preflight_accepts_playbook_recorder_without_entity_catalog() -> None:
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda domain, device_class: base_entities().get((domain, device_class), []),
        diagnose_power_meter=lambda _: PowerMeterDiagnostic(
            success=True,
            status=DiagnosticStatus.GOOD,
            precision_status=DiagnosticStatus.UNSUPPORTED,
            update_interval_status=DiagnosticStatus.UNSUPPORTED,
        ),
        developer_mode=True,
    )

    result = checker.validate(RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec()))

    assert result.warnings == []


def test_preflight_requires_entity_catalog_for_complex_recorder() -> None:
    checker = MeasurementPreflight(
        has_active_session=lambda: False,
        verify_storage=lambda: None,
        load_entities=lambda domain, device_class: base_entities().get((domain, device_class), []),
        diagnose_power_meter=lambda _: PowerMeterDiagnostic(
            success=True,
            status=DiagnosticStatus.GOOD,
            precision_status=DiagnosticStatus.UNSUPPORTED,
            update_interval_status=DiagnosticStatus.UNSUPPORTED,
        ),
        developer_mode=True,
    )
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.plug",),
    )

    with pytest.raises(PreflightError, match="entity metadata is unavailable"):
        checker.validate(request)


def test_preflight_accepts_generic_recorder_entity_from_complete_catalog() -> None:
    entities = base_entities()
    entities[("switch", None)] = [Entity("switch.plug", domain="switch")]
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.plug",),
    )

    assert preflight(entities).validate(request).warnings == []


def test_preflight_rejects_missing_complex_recorder_entity() -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=("switch.missing",),
    )

    checker = preflight(base_entities())
    with pytest.raises(PreflightError, match="does not exist"):
        checker.validate(request)


def test_preflight_rejects_unavailable_vacuum() -> None:
    entities = base_entities()
    # Keep the selected entity in the complete catalog while omitting it from the available vacuum choices.
    entities[(None, None)] = [Entity("vacuum.missing", domain="vacuum")]
    entities[("sensor", None)] = [Entity("sensor.robot_battery", state="42")]
    entities[(None, "battery")] = [Entity("sensor.robot_battery", state="42")]
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id="vacuum.missing",
        battery_entity_id="sensor.robot_battery",
    )

    checker = preflight(entities)
    with pytest.raises(PreflightError, match="vacuum is unavailable"):
        checker.validate(request)


@pytest.mark.parametrize(
    "battery_group, message",
    [
        ([], "battery sensor is unavailable"),
        ([Entity("sensor.robot_battery", device_id="other-device", state="42")], "same Home Assistant device"),
    ],
)
def test_preflight_rejects_unusable_vacuum_battery(battery_group: list[Entity], message: str) -> None:
    entities = base_entities()
    entities[("vacuum", None)] = [Entity("vacuum.test", device_id="robot-device")]
    entities[(None, "battery")] = battery_group
    # Retain the selection in the complete catalog so this exercises availability or relationship validation.
    entities[("sensor", None)] = battery_group or [Entity("sensor.robot_battery", state="unavailable")]
    request = RecorderMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id="vacuum.test",
        battery_entity_id="sensor.robot_battery",
    )

    checker = preflight(entities)
    with pytest.raises(PreflightError, match=message):
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

    validator = preflight(base_entities(), voltage_supported=None)
    with pytest.raises(PreflightError, match="Could not inspect voltage capability"):
        validator.validate(request)


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
    "measurement, message",
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


def _charging_request() -> ChargingMeasurementRequest:
    return ChargingMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassChargingControllerSpec(entity_id="vacuum.test"),
        charging_device_type="vacuum_robot",
    )


def test_preflight_rejects_missing_charging_battery_source() -> None:
    """Neither a battery sensor on the device nor the battery_level attribute is available."""
    entities = base_entities() | {("vacuum", None): [Entity("vacuum.test", attribute_names=[])]}

    validator = preflight(entities)
    request = _charging_request()
    with pytest.raises(PreflightError, match=r"battery_level is not available"):
        validator.validate(request)


@pytest.mark.parametrize("battery_level", ["0", "80", "100", "42.5"])
def test_preflight_accepts_charging_with_related_battery_sensor(battery_level: str) -> None:
    """A battery sensor on the same device is used even without the battery_level attribute."""
    entities = base_entities() | {
        ("vacuum", None): [Entity("vacuum.test", attribute_names=[], device_id="vacuum-device")],
        (None, "battery"): [Entity("sensor.vacuum_battery", state=battery_level, device_id="vacuum-device")],
    }

    result = preflight(entities).validate(_charging_request())

    assert result.warnings == []
    assert result.battery_level_entity_id == "sensor.vacuum_battery"
    assert result.battery_level_attribute is None


def test_preflight_reports_battery_level_attribute_fallback() -> None:
    result = preflight(base_entities()).validate(_charging_request())

    assert result.battery_level_entity_id is None
    assert result.battery_level_attribute == "battery_level"


def test_charging_ignores_battery_sensors_on_other_devices() -> None:
    entities = base_entities() | {
        ("vacuum", None): [Entity("vacuum.test", attribute_names=["battery_level"], device_id="vacuum-device")],
        (None, "battery"): [
            Entity("sensor.other_battery", state="unknown", device_id="other-device"),
            Entity("sensor.vacuum_battery", state="42", device_id="vacuum-device"),
        ],
    }

    result = preflight(entities).validate(_charging_request())

    assert result.battery_level_entity_id == "sensor.vacuum_battery"
    assert result.battery_level_attribute is None


@pytest.mark.parametrize("battery_level", ["unknown", "", "-1", "101", "nan", "inf"])
def test_preflight_rejects_invalid_related_battery_sensor(battery_level: str) -> None:
    entities = base_entities() | {
        ("vacuum", None): [Entity("vacuum.test", attribute_names=[], device_id="vacuum-device")],
        (None, "battery"): [Entity("sensor.vacuum_battery", state=battery_level, device_id="vacuum-device")],
    }

    validator = preflight(entities)
    request = _charging_request()
    with pytest.raises(PreflightError, match="numeric percentage"):
        validator.validate(request)


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

    assert result.supported_modes == [LutMode.BRIGHTNESS]
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

    assert result.supported_modes == [LutMode.BRIGHTNESS]
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


@pytest.mark.parametrize("effects,expected_variations", [(["colorloop"], 8), ([], 0)])
def test_effect_preflight_uses_recordable_effects(effects: list[str], expected_variations: int) -> None:
    entities = base_entities()
    entities[("light", None)] = [Entity("light.test", [LutMode.EFFECT], effect_list=effects)]
    request = LightMeasurementRequest(
        model_id="L122FF63H11A5.0W",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassLightControllerSpec(entity_id="light.test"),
        modes={LutMode.EFFECT},
    )

    result = preflight(entities).validate(request)

    assert result.estimated_variations == expected_variations
    assert result.estimated_duration_seconds == (1471 if effects else 0)


def test_multi_light_preflight_uses_common_capabilities_and_models() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity(
            "light.one",
            [LutMode.BRIGHTNESS, LutMode.COLOR_TEMP],
            min_mired=150,
            max_mired=400,
            model_id="LWA017",
        ),
        Entity(
            "light.two",
            [LutMode.BRIGHTNESS, LutMode.COLOR_TEMP],
            min_mired=200,
            max_mired=500,
            model_id="LWA017",
        ),
    ]
    request = LightMeasurementRequest(
        model_id="LWA017",
        product_name="Test lights",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassMultiLightControllerSpec(entity_ids=["light.one", "light.two"]),
        modes={LutMode.COLOR_TEMP},
        multiple_light_count=2,
    )

    result = preflight(entities).validate(request)

    assert result.warnings == []
    assert result.supported_modes == [LutMode.BRIGHTNESS, LutMode.COLOR_TEMP]


def test_multi_light_preflight_rejects_mixed_models_and_group_member_overlap() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity("light.group", [LutMode.BRIGHTNESS], member_entity_ids=["light.one", "light.two"]),
        Entity("light.one", [LutMode.BRIGHTNESS], model_id="ONE"),
        Entity("light.two", [LutMode.BRIGHTNESS], model_id="TWO"),
    ]
    common = {
        "model_id": "ONE",
        "product_name": "Test lights",
        "measure_device": "Test meter",
        "power_meter": HassPowerMeterSpec(entity_id="sensor.power"),
        "multiple_light_count": 3,
    }

    mixed = LightMeasurementRequest(
        **common,
        controller=HassMultiLightControllerSpec(entity_ids=["light.one", "light.two"]),
    )
    with pytest.raises(PreflightError, match="same model ID"):
        preflight(entities).validate(mixed)

    overlap = LightMeasurementRequest(
        **common,
        controller=HassMultiLightControllerSpec(entity_ids=["light.group", "light.one"]),
    )
    with pytest.raises(PreflightError, match="group and one of its members"):
        preflight(entities).validate(overlap)


def test_multi_light_preflight_warns_for_unknown_models_and_validates_count() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity("light.one", [LutMode.BRIGHTNESS]),
        Entity("light.two", [LutMode.BRIGHTNESS]),
    ]
    request = LightMeasurementRequest(
        model_id="manual",
        product_name="Test lights",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassMultiLightControllerSpec(entity_ids=["light.one", "light.two"]),
        multiple_light_count=2,
    )

    assert "Could not confirm" in preflight(entities).validate(request).warnings[0]
    with pytest.raises(PreflightError, match="Number of lights"):
        preflight(entities).validate(request.model_copy(update={"multiple_light_count": 1}))


def test_light_group_does_not_force_its_discovered_member_count() -> None:
    entities = base_entities()
    entities[("light", None)] = [
        Entity(
            "light.group",
            [LutMode.BRIGHTNESS],
            model_id="LWA017",
            member_entity_ids=["light.one", "light.two"],
        ),
        Entity("light.one", [LutMode.BRIGHTNESS], model_id="LWA017"),
        Entity("light.two", [LutMode.BRIGHTNESS], model_id="LWA017"),
    ]
    request = LightMeasurementRequest(
        model_id="LWA017",
        product_name="Test group",
        measure_device="Test meter",
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        controller=HassLightControllerSpec(entity_id="light.group"),
        multiple_light_count=1,
    )

    preflight(entities).validate(request)


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

    assert result.warnings == []
