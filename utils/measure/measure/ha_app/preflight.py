from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from measure.controller.charging.spec import HassChargingControllerSpec, charging_entity_domain
from measure.controller.fan.spec import HassFanControllerSpec
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightInfo
from measure.controller.light.spec import HassLightControllerSpec
from measure.controller.media.spec import HassMediaControllerSpec
from measure.home_assistant_entities import DeviceClass, EntityDomain
from measure.powermeter.spec import HassPowerMeterSpec
from measure.request import (
    ChargingMeasurementRequest,
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


class MeasurementPreflight:
    """Validate a request against current session, storage and entity state."""

    def __init__(
        self,
        *,
        has_active_session: Callable[[], bool],
        verify_storage: Callable[[], None],
        load_entities: EntityLoader,
    ) -> None:
        self._has_active_session = has_active_session
        self._verify_storage = verify_storage
        self._load_entities = load_entities

    def validate(self, request: MeasurementRequest) -> PreflightResult:
        """Return warnings and estimates, or raise a typed preflight error."""

        if self._has_active_session():
            raise ActiveSessionError("A measurement session is already active")
        try:
            self._verify_storage()
        except OSError as error:
            raise PreflightError("Persistent app storage is not writable") from error

        self._validate_power_meter(request)

        if isinstance(request, LightMeasurementRequest):
            return self._validate_light(request)
        self._validate_controller(request)
        return PreflightResult()

    def _validate_power_meter(self, request: MeasurementRequest) -> None:
        if not isinstance(request.power_meter, HassPowerMeterSpec):
            return
        powers = {entity.entity_id for entity in self._load_entities(None, DeviceClass.POWER)}
        if request.power_meter.entity_id not in powers:
            raise PreflightError("Selected power entity is unavailable or not measured in W")

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

    def _require_entity(self, entity_id: str | None, domain: EntityDomain, message: str) -> None:
        available = {entity.entity_id for entity in self._load_entities(domain, None)}
        if entity_id not in available:
            raise PreflightError(message)
