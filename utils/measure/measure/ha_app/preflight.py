from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from typing import Protocol

from measure.const import DUMMY_LOAD_MEASUREMENT_COUNT, DUMMY_LOAD_MEASUREMENTS_DURATION
from measure.controller.charging.const import ATTR_BATTERY_LEVEL
from measure.controller.charging.spec import HassChargingControllerSpec, charging_entity_domain
from measure.controller.fan.spec import HassFanControllerSpec
from measure.controller.light.capabilities import common_effects, merge_light_infos
from measure.controller.light.const import MAX_MIRED, MIN_MIRED, LutMode
from measure.controller.light.controller import LightInfo
from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import (
    DummyLightControllerSpec,
    HassLightControllerSpec,
    HassMultiLightControllerSpec,
    HueLightControllerSpec,
)
from measure.controller.media.spec import HassMediaControllerSpec
from measure.home_assistant_entities import DeviceClass, EntityDomain
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic
from measure.powermeter.spec import (
    DummyPowerMeterSpec,
    HassPowerMeterSpec,
    KasaPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
)
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
    device_id: str | None
    state: str
    attribute_names: list[str]
    supported_modes: list[LutMode] | None
    effect_list: list[str] | None
    min_mired: int | None
    max_mired: int | None
    model_id: str | None
    member_entity_ids: list[str]


EntityLoader = Callable[[EntityDomain | None, DeviceClass | None], Sequence[EntityRecord]]


@dataclass(frozen=True)
class PreflightResult:
    warnings: tuple[str, ...] = ()
    estimated_variations: int | None = None
    estimated_duration_seconds: int | None = None
    supported_modes: tuple[LutMode, ...] | None = None
    power_meter_diagnostic: PowerMeterDiagnostic | None = None
    battery_level_entity_id: str | None = None
    battery_level_attribute: str | None = None


MODEL_UNCONFIRMED_WARNING = (
    "Could not confirm that every selected light has the same model. Verify this before starting."
)


@dataclass(frozen=True)
class LightSelection:
    """The lights one request drives, reduced to the capabilities they all share."""

    lights: tuple[EntityRecord, ...]
    supported_modes: set[LutMode]
    light_info: LightInfo
    effects: list[str]


def _no_group_member_overlap(selection: LightSelection, _: LightMeasurementRequest) -> tuple[str, ...]:
    """A group already drives its members, so selecting both would measure them twice."""

    members = {member for light in selection.lights for member in light.member_entity_ids}
    if members & {light.entity_id for light in selection.lights}:
        raise PreflightError("A light group and one of its members cannot both be selected")
    return ()


def _count_covers_selection(selection: LightSelection, request: LightMeasurementRequest) -> tuple[str, ...]:
    """Measured power is divided by the count, so it cannot describe fewer lights than are driven."""

    if request.multiple_light_count < len(selection.lights):
        raise PreflightError("Number of lights cannot be lower than the number of selected lights")
    return ()


def _models_agree(selection: LightSelection, _: LightMeasurementRequest) -> tuple[str, ...]:
    """One profile is produced for all lights, so they must be the same model."""

    models = {light.model_id for light in selection.lights}
    if len(models - {None}) > 1:
        raise PreflightError("Selected lights must have the same model ID")
    if len(selection.lights) > 1 and None in models:
        return (MODEL_UNCONFIRMED_WARNING,)
    return ()


def _modes_supported(selection: LightSelection, request: LightMeasurementRequest) -> tuple[str, ...]:
    if not set(request.modes).issubset(selection.supported_modes):
        raise PreflightError("Selected light does not advertise every requested mode")
    return ()


def _color_temp_range_overlaps(selection: LightSelection, _: LightMeasurementRequest) -> tuple[str, ...]:
    if selection.light_info.min_mired > selection.light_info.max_mired:
        raise PreflightError("Selected lights do not share a color temperature range")
    return ()


LightRule = Callable[[LightSelection, LightMeasurementRequest], tuple[str, ...]]

#: Checks applied to a light selection, in order. Each returns warnings or raises a PreflightError,
#: so a new condition is added here rather than by growing the caller.
LIGHT_RULES: tuple[LightRule, ...] = (
    _no_group_member_overlap,
    _count_covers_selection,
    _models_agree,
    _modes_supported,
    _color_temp_range_overlaps,
)


def _light_info(light: EntityRecord) -> LightInfo:
    return LightInfo(
        "unknown",
        min_mired=light.min_mired if light.min_mired is not None else MIN_MIRED,
        max_mired=light.max_mired if light.max_mired is not None else MAX_MIRED,
    )


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
        diagnostic = self._diagnose_dummy_load(request)

        if isinstance(request, LightMeasurementRequest):
            result = self._validate_light(request)
        else:
            result = self._validate_controller(request)

        warnings = list(result.warnings)
        duration = result.estimated_duration_seconds
        if isinstance(request.dummy_load, DummyLoadCalibrationRequest):
            warnings.append(
                "Dummy-load calibration takes at least 10 minutes and repeats until the resistance is stable.",
            )
            duration = (duration or 0) + DUMMY_LOAD_MEASUREMENT_COUNT * DUMMY_LOAD_MEASUREMENTS_DURATION

        diagnostic = self._collect_power_meter_diagnostic(request, diagnostic, warnings)

        return PreflightResult(
            warnings=tuple(warnings),
            estimated_variations=result.estimated_variations,
            estimated_duration_seconds=duration,
            supported_modes=result.supported_modes,
            power_meter_diagnostic=diagnostic,
            battery_level_entity_id=result.battery_level_entity_id,
            battery_level_attribute=result.battery_level_attribute,
        )

    def _diagnose_dummy_load(self, request: MeasurementRequest) -> PowerMeterDiagnostic | None:
        """Diagnose the power meter upfront when a dummy load is used, so its voltage support can be validated."""
        if request.dummy_load is None or self._diagnose_power_meter is None:
            return None

        diagnostic = self._diagnose_power_meter(request.power_meter)
        self._validate_dummy_load_voltage(diagnostic)
        return diagnostic

    def _collect_power_meter_diagnostic(
        self,
        request: MeasurementRequest,
        diagnostic: PowerMeterDiagnostic | None,
        warnings: list[str],
    ) -> PowerMeterDiagnostic | None:
        """Diagnose the power meter when not done yet and translate the result into an error or warnings."""
        if self._diagnose_power_meter is None:
            return diagnostic

        if diagnostic is None:
            diagnostic = self._diagnose_power_meter(request.power_meter)
        if not diagnostic.success:
            raise PreflightError(diagnostic.message or "Could not read from the power meter")
        if diagnostic.status in {DiagnosticStatus.WARNING, DiagnosticStatus.POOR}:
            warnings.extend(diagnostic.messages)
        return diagnostic

    def _validate_adapters(self, request: MeasurementRequest) -> None:
        power_meter = request.power_meter
        if isinstance(power_meter, DummyPowerMeterSpec):
            if not self._developer_mode:
                raise PreflightError("Dummy power meters require developer mode in the Home Assistant app")
        elif not isinstance(power_meter, HassPowerMeterSpec | ShellyPowerMeterSpec | KasaPowerMeterSpec):
            label = power_meter.type.value.replace("_", " ").title()
            raise PreflightError(f"{label} power meters are not supported by the Home Assistant app")

        controller = request.controller
        if controller is None:
            return
        if controller.is_dummy:
            if not self._developer_mode:
                raise PreflightError("Dummy controllers require developer mode in the Home Assistant app")
            return
        if isinstance(
            controller,
            HassLightControllerSpec
            | HassMultiLightControllerSpec
            | HassMediaControllerSpec
            | HassChargingControllerSpec
            | HassFanControllerSpec,
        ):
            return
        if isinstance(controller, HueLightControllerSpec):
            raise PreflightError("Hue light controllers are not supported by the Home Assistant app")
        raise PreflightError(f"{type(controller).__name__} is not supported by the Home Assistant app")

    def _validate_power_meter(self, request: MeasurementRequest) -> None:
        power_meter = request.power_meter
        if not isinstance(power_meter, HassPowerMeterSpec):
            return
        powers = {entity.entity_id for entity in self._load_entities(None, DeviceClass.POWER)}
        if power_meter.entity_id not in powers:
            raise PreflightError("Selected power entity is unavailable or not measured in W")
        if request.dummy_load is not None and not power_meter.voltage_entity_id:
            raise PreflightError("A voltage sensor is required when using a resistive dummy load")
        if power_meter.voltage_entity_id:
            voltages = {entity.entity_id for entity in self._load_entities(None, DeviceClass.VOLTAGE)}
            if power_meter.voltage_entity_id not in voltages:
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

    def _validate_controller(self, request: MeasurementRequest) -> PreflightResult:
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
                charging_entity = self._require_entity(
                    request.controller.entity_id,
                    domain,
                    "Selected charging device is unavailable",
                )
                return self._validate_charging_battery_source(charging_entity)
        return PreflightResult()

    def _validate_charging_battery_source(self, charging_entity: EntityRecord) -> PreflightResult:
        # Prefer a separate battery sensor on the same device (the modern HA default),
        # falling back to the battery_level attribute when none is available.
        battery_sensor = self._find_related_battery_sensor(charging_entity)
        if battery_sensor is not None:
            try:
                level = float(battery_sensor.state)
            except ValueError, TypeError:
                level = math.nan
            if not math.isfinite(level) or not 0 <= level <= 100:
                raise PreflightError("Battery level sensor must report a numeric percentage between 0 and 100")
            return PreflightResult(battery_level_entity_id=battery_sensor.entity_id)

        if ATTR_BATTERY_LEVEL in charging_entity.attribute_names:
            return PreflightResult(battery_level_attribute=ATTR_BATTERY_LEVEL)
        raise PreflightError(
            f"No battery level sensor was found on the same device, and attribute "
            f"{ATTR_BATTERY_LEVEL} is not available on the charging device",
        )

    def _find_related_battery_sensor(self, charging_entity: EntityRecord) -> EntityRecord | None:
        """Return a battery sensor on the same device as the charging entity, if any."""

        if charging_entity.device_id is None:
            return None
        return next(
            (
                sensor
                for sensor in self._load_entities(None, DeviceClass.BATTERY)
                if sensor.device_id == charging_entity.device_id
            ),
            None,
        )

    def _validate_light(self, request: LightMeasurementRequest) -> PreflightResult:
        if isinstance(request.controller, DummyLightControllerSpec):
            return self._estimate_dummy_light(request)
        if not isinstance(request.controller, HassLightControllerSpec | HassMultiLightControllerSpec):
            raise PreflightError("Selected light entity is unavailable")

        selection = self._resolve_lights(request.controller.entity_ids)
        warnings = tuple(warning for rule in LIGHT_RULES for warning in rule(selection, request))
        plan = build_light_plan(request.modes, request.parameters, selection.light_info, selection.effects)
        return PreflightResult(
            warnings=warnings,
            estimated_variations=plan.variation_count,
            estimated_duration_seconds=round(estimate_light_time_left(plan, request.parameters)),
            supported_modes=tuple(sorted(selection.supported_modes, key=str)),
        )

    def _resolve_lights(self, entity_ids: Sequence[str]) -> LightSelection:
        """Look the selected lights up in the catalog and reduce them to their shared capabilities."""

        lights = {entity.entity_id: entity for entity in self._load_entities(EntityDomain.LIGHT, None)}
        selected = [lights[entity_id] for entity_id in entity_ids if entity_id in lights]
        if len(selected) != len(entity_ids):
            raise PreflightError("Selected light entity is unavailable")
        return LightSelection(
            lights=tuple(selected),
            supported_modes=set.intersection(*(set(light.supported_modes or []) for light in selected)),
            light_info=merge_light_infos([_light_info(light) for light in selected]),
            effects=common_effects([light.effect_list or [] for light in selected]),
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

    def _require_entity(self, entity_id: str | None, domain: EntityDomain, message: str) -> EntityRecord:
        available = {entity.entity_id: entity for entity in self._load_entities(domain, None)}
        entity = available.get(entity_id or "")
        if entity is None:
            raise PreflightError(message)
        return entity
