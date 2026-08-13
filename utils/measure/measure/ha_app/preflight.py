from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from typing import Protocol

from measure.const import DUMMY_LOAD_MEASUREMENT_COUNT, DUMMY_LOAD_MEASUREMENTS_DURATION
from measure.controller.charging.const import ATTR_BATTERY_LEVEL
from measure.controller.charging.spec import HassChargingControllerSpec, charging_entity_domain
from measure.controller.fan.spec import HassFanControllerSpec
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

    def _validate_light(self, request: LightMeasurementRequest) -> PreflightResult:  # noqa: C901
        if isinstance(request.controller, DummyLightControllerSpec):
            return self._estimate_dummy_light(request)
        if not isinstance(request.controller, HassLightControllerSpec | HassMultiLightControllerSpec):
            raise PreflightError("Selected light entity is unavailable")
        lights = {entity.entity_id: entity for entity in self._load_entities(EntityDomain.LIGHT, None)}
        entity_ids = (
            request.controller.entity_ids
            if isinstance(request.controller, HassMultiLightControllerSpec)
            else [request.controller.entity_id]
        )
        selected = [lights[entity_id] for entity_id in entity_ids if entity_id in lights]
        if len(selected) != len(entity_ids):
            raise PreflightError("Selected light entity is unavailable")
        if isinstance(request.power_meter, HassPowerMeterSpec) and request.power_meter.voltage_entity_id:
            voltages = {entity.entity_id for entity in self._load_entities(None, DeviceClass.VOLTAGE)}
            if request.power_meter.voltage_entity_id not in voltages:
                raise PreflightError("Selected voltage entity is unavailable or not measured in V")
        expanded = self._expand_selected_lights(selected, lights)
        leaves = list({light.entity_id: light for light in expanded}.values())
        if len(leaves) != len(expanded):
            raise PreflightError("A light group and one of its members cannot both be selected")
        if request.multiple_light_count < len(selected):
            raise PreflightError("Number of lights cannot be lower than the number of selected lights")
        model_ids = {model_id for light in leaves if (model_id := getattr(light, "model_id", None))}
        if len(model_ids) > 1:
            raise PreflightError("Selected lights must have the same model ID")
        models_confirmed = len(model_ids) == 1 and all(getattr(light, "model_id", None) for light in leaves)
        warnings = (
            ("Could not confirm that every selected light has the same model. Verify this before starting.",)
            if len(leaves) > 1 and not models_confirmed
            else ()
        )
        supported_sets = [set(light.supported_modes or []) for light in selected]
        supported = set.intersection(*supported_sets)
        if not set(request.modes).issubset(supported):
            raise PreflightError("Selected light does not advertise every requested mode")
        min_mired = max(light.min_mired if light.min_mired is not None else MIN_MIRED for light in selected)
        max_mired = min(light.max_mired if light.max_mired is not None else MAX_MIRED for light in selected)
        if min_mired > max_mired:
            raise PreflightError("Selected lights do not share a color temperature range")
        light_info = LightInfo(
            "unknown",
            min_mired=min_mired,
            max_mired=max_mired,
        )
        effects = list(selected[0].effect_list or ())
        for light in selected[1:]:
            effects = [effect for effect in effects if effect in (light.effect_list or ())]
        plan = build_light_plan(request.modes, request.parameters, light_info, effects)
        return PreflightResult(
            warnings=warnings,
            estimated_variations=plan.variation_count,
            estimated_duration_seconds=round(estimate_light_time_left(plan, request.parameters)),
            supported_modes=tuple(sorted(supported, key=str)),
        )

    @staticmethod
    def _expand_selected_lights(
        selected: Sequence[EntityRecord],
        lights: dict[str, EntityRecord],
    ) -> list[EntityRecord]:
        leaves: list[EntityRecord] = []

        def visit(light: EntityRecord, path: frozenset[str]) -> None:
            if light.entity_id in path:
                raise PreflightError("Selected light groups contain a cycle")
            member_ids = getattr(light, "member_entity_ids", [])
            if any(entity_id not in lights for entity_id in member_ids):
                raise PreflightError("A selected light group contains an unavailable member")
            members = [lights[entity_id] for entity_id in member_ids if entity_id in lights]
            if not members:
                leaves.append(light)
                return
            for member in members:
                visit(member, path | {light.entity_id})

        for light in selected:
            visit(light, frozenset())
        return leaves

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
