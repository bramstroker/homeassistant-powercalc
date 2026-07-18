from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from measure.const import DUMMY_LOAD_MEASUREMENT_COUNT, DUMMY_LOAD_MEASUREMENTS_DURATION
from measure.controller.charging.spec import (
    DummyChargingControllerSpec,
    HassChargingControllerSpec,
    charging_entity_domain,
)
from measure.controller.fan.spec import DummyFanControllerSpec, HassFanControllerSpec
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightInfo
from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import DummyLightControllerSpec, HassLightControllerSpec, HueLightControllerSpec
from measure.controller.media.spec import DummyMediaControllerSpec, HassMediaControllerSpec
from measure.home_assistant_entities import DeviceClass, EntityDomain
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, PowerMeterSpec, ShellyPowerMeterSpec
from measure.request import (
    ChargingMeasurementRequest,
    DummyLoadCalibrationRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    SpeakerMeasurementRequest,
)
from measure.runner.light_plan import build_light_plan, estimate_light_time_left


class PreflightError(Exception):
    """Raised when a validated request cannot run against current external state."""


class ActiveSessionError(PreflightError):
    """Raised when a new measurement conflicts with the active session."""


class EntityRecord(Protocol):
    entity_id: str
    supported_modes: list[LutMode] | None
    effect_list: list[str] | None
    min_mired: int | None
    max_mired: int | None


EntityLoader = Callable[[EntityDomain | None, DeviceClass | None], Sequence[EntityRecord]]


@dataclass(frozen=True)
class PreflightResult:
    warnings: tuple[str, ...] = ()
    estimated_variations: int | None = None
    estimated_duration_seconds: int | None = None
    supported_modes: tuple[LutMode, ...] | None = None
    power_meter_diagnostic: PowerMeterDiagnostic | None = None


class MeasurementPreflight:
    """Validate a request against current session, storage and entity state."""

    def __init__(
        self,
        *,
        has_active_session: Callable[[], bool],
        verify_storage: Callable[[], None],
        load_entities: EntityLoader,
        diagnose_power_meter: Callable[[PowerMeterSpec], PowerMeterDiagnostic] | None = None,
        developer_mode: bool = False,
    ) -> None:
        self._has_active_session = has_active_session
        self._verify_storage = verify_storage
        self._load_entities = load_entities
        self._diagnose_power_meter = diagnose_power_meter
        self._developer_mode = developer_mode

    def validate(self, request: MeasurementRequest) -> PreflightResult:
        """Return warnings and estimates, or raise a typed preflight error."""

        self._validate_adapters(request)
        if self._has_active_session():
            raise ActiveSessionError("A measurement session is already active")
        try:
            self._verify_storage()
        except OSError as error:
            raise PreflightError("Persistent app storage is not writable") from error

        self._validate_power_meter(request)
        diagnostic: PowerMeterDiagnostic | None = None
        if request.dummy_load is not None and self._diagnose_power_meter is not None:
            diagnostic = self._diagnose_power_meter(request.power_meter)
            self._validate_dummy_load_voltage(diagnostic)

        if isinstance(request, LightMeasurementRequest):
            result = self._validate_light(request)
        else:
            self._validate_controller(request)
            result = PreflightResult()

        warnings = list(result.warnings)
        duration = result.estimated_duration_seconds
        if isinstance(request.dummy_load, DummyLoadCalibrationRequest):
            warnings.append(
                "Dummy-load calibration takes at least 10 minutes and repeats until the resistance is stable.",
            )
            duration = (duration or 0) + DUMMY_LOAD_MEASUREMENT_COUNT * DUMMY_LOAD_MEASUREMENTS_DURATION

        if self._diagnose_power_meter is not None:
            if diagnostic is None:
                diagnostic = self._diagnose_power_meter(request.power_meter)
            if not diagnostic.success:
                raise PreflightError(diagnostic.message or "Could not read from the power meter")
            if diagnostic.status in {DiagnosticStatus.WARNING, DiagnosticStatus.POOR}:
                warnings.extend(diagnostic.messages)

        return PreflightResult(
            warnings=tuple(warnings),
            estimated_variations=result.estimated_variations,
            estimated_duration_seconds=duration,
            supported_modes=result.supported_modes,
            power_meter_diagnostic=diagnostic,
        )

    def _validate_adapters(self, request: MeasurementRequest) -> None:
        power_meter = request.power_meter
        if isinstance(power_meter, DummyPowerMeterSpec):
            if not self._developer_mode:
                raise PreflightError("Dummy power meters require developer mode in the Home Assistant app")
        elif not isinstance(power_meter, HassPowerMeterSpec | ShellyPowerMeterSpec):
            label = power_meter.type.value.replace("_", " ").title()
            raise PreflightError(f"{label} power meters are not supported by the Home Assistant app")

        controller = None
        if isinstance(
            request,
            LightMeasurementRequest | SpeakerMeasurementRequest | ChargingMeasurementRequest | FanMeasurementRequest,
        ):
            controller = request.controller
        if controller is None:
            return
        if isinstance(
            controller,
            DummyLightControllerSpec | DummyMediaControllerSpec | DummyChargingControllerSpec | DummyFanControllerSpec,
        ):
            if not self._developer_mode:
                raise PreflightError("Dummy controllers require developer mode in the Home Assistant app")
            return
        if isinstance(
            controller,
            HassLightControllerSpec | HassMediaControllerSpec | HassChargingControllerSpec | HassFanControllerSpec,
        ):
            return
        if isinstance(controller, HueLightControllerSpec):
            raise PreflightError("Hue light controllers are not supported by the Home Assistant app")
        raise PreflightError(f"{type(controller).__name__} is not supported by the Home Assistant app")

    def _validate_power_meter(self, request: MeasurementRequest) -> None:
        if isinstance(request.power_meter, HassPowerMeterSpec):
            powers = {entity.entity_id for entity in self._load_entities(None, DeviceClass.POWER)}
            if request.power_meter.entity_id not in powers:
                raise PreflightError("Selected power entity is unavailable or not measured in W")
        if request.dummy_load is None:
            return
        if isinstance(request.power_meter, HassPowerMeterSpec):
            if not request.power_meter.voltage_entity_id:
                raise PreflightError("A voltage sensor is required when using a resistive dummy load")
            voltages = {entity.entity_id for entity in self._load_entities(None, DeviceClass.VOLTAGE)}
            if request.power_meter.voltage_entity_id not in voltages:
                raise PreflightError("Selected voltage entity is unavailable or not measured in V")

    @staticmethod
    def _validate_dummy_load_voltage(diagnostic: PowerMeterDiagnostic) -> None:
        if diagnostic.supports_voltage is False:
            raise PreflightError(
                "The selected power meter does not support voltage measurements required for dummy loads",
            )
        if diagnostic.supports_voltage is None:
            if not diagnostic.success:
                raise PreflightError(diagnostic.message or "Could not read from the power meter")
            raise PreflightError(
                "Could not determine whether the selected power meter supports voltage measurements "
                "required for dummy loads",
            )

    def _validate_controller(self, request: MeasurementRequest) -> None:
        if isinstance(request, SpeakerMeasurementRequest):
            if isinstance(request.controller, HassMediaControllerSpec):
                self._require_entity(
                    request.controller.entity_id,
                    EntityDomain.MEDIA_PLAYER,
                    "Selected media player is unavailable",
                )
        elif isinstance(request, FanMeasurementRequest):
            if isinstance(request.controller, HassFanControllerSpec):
                self._require_entity(request.controller.entity_id, EntityDomain.FAN, "Selected fan is unavailable")
        elif isinstance(request, ChargingMeasurementRequest):
            domain = EntityDomain(charging_entity_domain(request.charging_device_type))
            if isinstance(request.controller, HassChargingControllerSpec):
                if not request.controller.entity_id.startswith(f"{domain}."):
                    raise PreflightError("Charging device type does not match the selected entity")
                self._require_entity(request.controller.entity_id, domain, "Selected charging device is unavailable")

    def _validate_light(self, request: LightMeasurementRequest) -> PreflightResult:
        if isinstance(request.controller, DummyLightControllerSpec):
            return self._estimate_dummy_light(request)
        if not isinstance(request.controller, HassLightControllerSpec):
            raise PreflightError("Selected light entity is unavailable")
        lights = {entity.entity_id: entity for entity in self._load_entities(EntityDomain.LIGHT, None)}
        light = lights.get(request.controller.entity_id)
        if light is None:
            raise PreflightError("Selected light entity is unavailable")
        if isinstance(request.power_meter, HassPowerMeterSpec) and request.power_meter.voltage_entity_id:
            voltages = {entity.entity_id for entity in self._load_entities(None, DeviceClass.VOLTAGE)}
            if request.power_meter.voltage_entity_id not in voltages:
                raise PreflightError("Selected voltage entity is unavailable or not measured in V")
        supported = set(light.supported_modes or [])
        if not set(request.modes).issubset(supported):
            raise PreflightError("Selected light does not advertise every requested mode")
        light_info = LightInfo(
            "unknown",
            min_mired=light.min_mired if light.min_mired is not None else MIN_MIRED,
            max_mired=light.max_mired if light.max_mired is not None else MAX_MIRED,
        )
        plan = build_light_plan(request.modes, request.parameters, light_info, light.effect_list or ())
        return PreflightResult(
            estimated_variations=plan.variation_count,
            estimated_duration_seconds=round(estimate_light_time_left(plan, request.parameters)),
            supported_modes=tuple(sorted(supported, key=str)),
        )

    @staticmethod
    def _estimate_dummy_light(request: LightMeasurementRequest) -> PreflightResult:
        controller = DummyLightController()
        plan = build_light_plan(
            request.modes,
            request.parameters,
            controller.get_light_info(),
            controller.get_effect_list(),
        )
        return PreflightResult(
            estimated_variations=plan.variation_count,
            estimated_duration_seconds=round(estimate_light_time_left(plan, request.parameters)),
            supported_modes=tuple(sorted(request.modes, key=str)),
        )

    def _require_entity(self, entity_id: str | None, domain: EntityDomain, message: str) -> None:
        available = {entity.entity_id for entity in self._load_entities(domain, None)}
        if entity_id not in available:
            raise PreflightError(message)
