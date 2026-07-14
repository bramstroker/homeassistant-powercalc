from __future__ import annotations

from collections.abc import Callable
from typing import Any

from measure.controller.charging.const import ATTR_BATTERY_LEVEL, BatteryLevelSourceType
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.dummy import DummyChargingController
from measure.controller.charging.hass import HassChargingController
from measure.controller.charging.spec import (
    ChargingControllerSpec,
    DummyChargingControllerSpec,
    HassChargingControllerSpec,
)
from measure.controller.fan.controller import FanController
from measure.controller.fan.dummy import DummyFanController
from measure.controller.fan.hass import HassFanController
from measure.controller.fan.spec import DummyFanControllerSpec, FanControllerSpec, HassFanControllerSpec
from measure.controller.light.controller import LightController
from measure.controller.light.dummy import DummyLightController
from measure.controller.light.hass import HassLightController
from measure.controller.light.hue import HueLightController
from measure.controller.light.spec import (
    DummyLightControllerSpec,
    HassLightControllerSpec,
    HueLightControllerSpec,
    LightControllerSpec,
)
from measure.controller.media.controller import MediaController
from measure.controller.media.dummy import DummyMediaController
from measure.controller.media.hass import HassMediaController
from measure.controller.media.spec import DummyMediaControllerSpec, HassMediaControllerSpec, MediaControllerSpec
from measure.execution import PreparedMeasurement, RunInteraction
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.hass import HassPowerMeter
from measure.powermeter.kasa import KasaPowerMeter
from measure.powermeter.manual import ManualPowerMeter
from measure.powermeter.mystrom import MyStromPowerMeter
from measure.powermeter.ocr import OcrPowerMeter
from measure.powermeter.powermeter import PowerMeter
from measure.powermeter.shelly import ShellyPowerMeter
from measure.powermeter.spec import (
    DummyPowerMeterSpec,
    HassPowerMeterSpec,
    KasaPowerMeterSpec,
    ManualPowerMeterSpec,
    MyStromPowerMeterSpec,
    OcrPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
    TasmotaPowerMeterSpec,
    TuyaPowerMeterSpec,
)
from measure.powermeter.tasmota import TasmotaPowerMeter
from measure.powermeter.tuya import TuyaPowerMeter
from measure.request import (
    AverageMeasurementRequest,
    ChargingMeasurementRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    RecorderMeasurementRequest,
    ResumePolicy,
    SpeakerMeasurementRequest,
)
from measure.runner.average import AverageRunner
from measure.runner.charging import ChargingRunner
from measure.runner.fan import FanRunner
from measure.runner.light import LightRunner
from measure.runner.recorder import RecorderRunner
from measure.runner.runner import MeasurementRunner
from measure.runner.speaker import SpeakerRunner
from measure.tuning import MeasurementParameters
from measure.util.measure_util import MeasureUtil


class MeasurementAssembler:
    """Build runners and device adapters from transport-neutral specifications."""

    def __init__(
        self,
        interaction: RunInteraction,
        *,
        home_assistant: HomeAssistantManager | None = None,
        tuya_device_key: str | None = None,
        power_meter_decorator: Callable[[PowerMeter], PowerMeter] | None = None,
    ) -> None:
        self._interaction = interaction
        self._home_assistant_manager = home_assistant
        self._tuya_device_key = tuya_device_key
        self._power_meter_decorator = power_meter_decorator

    def assemble(self, request: MeasurementRequest) -> PreparedMeasurement:
        """Resolve a request once into a transport-independent runner graph."""

        power_meter = self._power_meter(request.power_meter)
        if self._power_meter_decorator is not None:
            power_meter = self._power_meter_decorator(power_meter)
        voltage_enabled = power_meter.has_voltage_support()
        parameters = request.parameters
        measure_util = MeasureUtil(
            power_meter,
            parameters,
            include_voltage=lambda: voltage_enabled,
            wait=self._interaction.wait,
            interaction=self._interaction,
        )
        runner = self._runner(request, parameters, measure_util)
        return PreparedMeasurement(
            request=request,
            runner=runner,
        )

    def _power_meter(self, spec: PowerMeterSpec) -> PowerMeter:  # noqa: C901
        if isinstance(spec, DummyPowerMeterSpec):
            return DummyPowerMeter()
        if isinstance(spec, HassPowerMeterSpec):
            hass = self._home_assistant()
            return HassPowerMeter(
                hass,
                spec.call_update_entity,
                entity_id=spec.entity_id,
                voltage_entity_id=spec.voltage_entity_id,
                wait=self._interaction.wait,
            )
        if isinstance(spec, KasaPowerMeterSpec):
            return KasaPowerMeter(spec.device_ip)
        if isinstance(spec, ManualPowerMeterSpec):
            return ManualPowerMeter()
        if isinstance(spec, MyStromPowerMeterSpec):
            return MyStromPowerMeter(spec.device_ip)
        if isinstance(spec, OcrPowerMeterSpec):
            return OcrPowerMeter()
        if isinstance(spec, ShellyPowerMeterSpec):
            return ShellyPowerMeter(spec.device_ip, spec.timeout)
        if isinstance(spec, TasmotaPowerMeterSpec):
            return TasmotaPowerMeter(spec.device_ip)
        if isinstance(spec, TuyaPowerMeterSpec):
            if self._tuya_device_key is None:
                raise PowerMeterError("Tuya device key is required")
            return TuyaPowerMeter(spec.device_id, spec.device_ip, self._tuya_device_key, spec.version)
        raise PowerMeterError(f"Unsupported power meter specification: {type(spec).__name__}")

    def _runner(
        self,
        request: MeasurementRequest,
        parameters: MeasurementParameters,
        measure_util: MeasureUtil,
    ) -> MeasurementRunner[Any]:
        interaction = self._interaction
        if isinstance(request, LightMeasurementRequest):
            light_controller = self._light_controller(request.controller)
            return LightRunner(
                measure_util,
                parameters,
                light_controller,
                interaction,
                resume=request.resume_policy == ResumePolicy.RESUME,
            )
        if isinstance(request, SpeakerMeasurementRequest):
            media_controller = self._media_controller(request.controller)
            return SpeakerRunner(measure_util, parameters, media_controller, interaction)
        if isinstance(request, RecorderMeasurementRequest):
            return RecorderRunner(measure_util, interaction)
        if isinstance(request, AverageMeasurementRequest):
            return AverageRunner(measure_util, interaction=interaction)
        if isinstance(request, ChargingMeasurementRequest):
            charging_spec = request.controller
            charging_controller = self._charging_controller(charging_spec)
            battery_level_attribute: str | None = ATTR_BATTERY_LEVEL
            if isinstance(charging_spec, HassChargingControllerSpec):
                battery_level_attribute = (
                    charging_spec.battery_level_attribute or ATTR_BATTERY_LEVEL
                    if charging_spec.battery_level_source_type == BatteryLevelSourceType.ATTRIBUTE
                    else None
                )
            return ChargingRunner(
                measure_util,
                parameters,
                charging_controller,
                interaction,
                battery_level_attribute=battery_level_attribute,
            )
        if isinstance(request, FanMeasurementRequest):
            fan_controller = self._fan_controller(request.controller)
            return FanRunner(measure_util, fan_controller, interaction)
        raise ValueError(f"Unsupported measurement request: {type(request).__name__}")

    def _light_controller(self, spec: LightControllerSpec) -> LightController:
        if isinstance(spec, DummyLightControllerSpec):
            return DummyLightController()
        if isinstance(spec, HassLightControllerSpec):
            hass = self._home_assistant()
            return HassLightController(
                hass,
                spec.transition_time,
                entity_id=spec.entity_id,
                wait=self._interaction.wait,
            )
        if isinstance(spec, HueLightControllerSpec):
            return HueLightController(spec.bridge_ip, light=spec.light)
        raise ValueError(f"Expected a light controller specification, got {type(spec).__name__}")

    def _media_controller(self, spec: MediaControllerSpec) -> MediaController:
        if isinstance(spec, DummyMediaControllerSpec):
            return DummyMediaController()
        if isinstance(spec, HassMediaControllerSpec):
            hass = self._home_assistant()
            return HassMediaController(hass, entity_id=spec.entity_id)
        raise ValueError(f"Expected a media controller specification, got {type(spec).__name__}")

    def _charging_controller(self, spec: ChargingControllerSpec) -> ChargingController:
        if isinstance(spec, DummyChargingControllerSpec):
            return DummyChargingController()
        if isinstance(spec, HassChargingControllerSpec):
            hass = self._home_assistant()
            return HassChargingController(
                hass,
                entity_id=spec.entity_id,
                battery_level_source_type=spec.battery_level_source_type,
                battery_level_attribute=spec.battery_level_attribute,
                battery_level_entity_id=spec.battery_level_entity_id,
            )
        raise ValueError(f"Expected a charging controller specification, got {type(spec).__name__}")

    def _fan_controller(self, spec: FanControllerSpec) -> FanController:
        if isinstance(spec, DummyFanControllerSpec):
            return DummyFanController()
        if isinstance(spec, HassFanControllerSpec):
            hass = self._home_assistant()
            return HassFanController(hass, entity_id=spec.entity_id)
        raise ValueError(f"Expected a fan controller specification, got {type(spec).__name__}")

    def _home_assistant(self) -> HomeAssistantManager:
        if self._home_assistant_manager is None:
            raise ValueError("Home Assistant runtime connection is required")
        return self._home_assistant_manager
