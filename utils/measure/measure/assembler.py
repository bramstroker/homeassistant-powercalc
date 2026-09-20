from collections.abc import Callable, Mapping, Sequence
from typing import Any, assert_never

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
from measure.controller.light.spec import (
    DummyLightControllerSpec,
    HassLightControllerSpec,
    HassMultiLightControllerSpec,
    HueLightControllerSpec,
    LightControllerSpec,
)
from measure.controller.media.controller import MediaController
from measure.controller.media.dummy import DummyMediaController
from measure.controller.media.hass import HassMediaController
from measure.controller.media.spec import DummyMediaControllerSpec, HassMediaControllerSpec, MediaControllerSpec
from measure.execution import (
    DummyLoadCalibrationStore,
    DummyLoadPreparation,
    MeasurementPreparation,
    PreparedMeasurement,
)
from measure.home_assistant.client import HomeAssistantManager
from measure.home_assistant.entities import HomeAssistantEntityCatalog
from measure.powermeter.credentials import TapoCredentials
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.hass import HassPowerMeter
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
    OwonOwh98xxPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
    TasmotaPowerMeterSpec,
    TuyaPowerMeterSpec,
)
from measure.powermeter.tasmota import TasmotaPowerMeter
from measure.recording.context import build_recording_context
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
from measure.runner.interaction import RunInteraction
from measure.runner.light.runner import LightRunner
from measure.runner.recorder import EntityStateReader, RecorderEntityState, RecorderRunner
from measure.runner.runner import MeasurementRunner
from measure.runner.speaker import SpeakerRunner
from measure.tuning import MeasurementParameters
from measure.utils.sampling import PowerSampler


class MeasurementAssembler:
    """Build runners and device adapters from transport-neutral specifications."""

    def __init__(
        self,
        interaction: RunInteraction,
        *,
        home_assistant: HomeAssistantManager | None = None,
        tuya_device_key: str | None = None,
        shelly_password: str | None = None,
        kasa_credentials: TapoCredentials | None = None,
        on_sample: Callable[[float], None] | None = None,
        on_calibration_sample: Callable[[float, float, float], None] | None = None,
        dummy_load_calibration_store: DummyLoadCalibrationStore | None = None,
    ) -> None:
        self._interaction = interaction
        self._home_assistant_manager = home_assistant
        self._tuya_device_key = tuya_device_key
        self._shelly_password = shelly_password
        self._kasa_credentials = kasa_credentials
        self._on_sample = on_sample
        self._on_calibration_sample = on_calibration_sample
        self._dummy_load_calibration_store = dummy_load_calibration_store

    def assemble(self, request: MeasurementRequest) -> PreparedMeasurement:
        """Resolve a request once into a transport-independent runner graph."""

        power_meter = self.create_power_meter(request.power_meter)
        voltage_enabled = power_meter.has_voltage_support()
        parameters = request.parameters
        sampler = PowerSampler(
            power_meter,
            parameters,
            include_voltage=lambda: voltage_enabled,
            wait=self._interaction.wait,
            on_sample=self._on_sample,
            on_calibration_sample=self._on_calibration_sample,
        )
        runner = self.create_runner(request, parameters, sampler)
        preparations: list[MeasurementPreparation] = (
            [
                DummyLoadPreparation(
                    request=request,
                    spec=request.dummy_load,
                    sampler=sampler,
                    calibration_store=self._dummy_load_calibration_store,
                ),
            ]
            if request.dummy_load is not None
            else []
        )
        return PreparedMeasurement(
            request=request,
            runner=runner,
            preparations=preparations,
            interaction=self._interaction,
        )

    def create_power_meter(self, spec: PowerMeterSpec) -> PowerMeter:  # noqa: C901
        """Build the configured meter for execution or preflight diagnostics."""

        if isinstance(spec, DummyPowerMeterSpec):
            return DummyPowerMeter()
        if isinstance(spec, HassPowerMeterSpec):
            hass = self._require_home_assistant()
            return HassPowerMeter(
                hass,
                spec.call_update_entity,
                entity_id=spec.entity_id,
                voltage_entity_id=spec.voltage_entity_id,
                wait=self._interaction.wait,
            )
        if isinstance(spec, KasaPowerMeterSpec):
            from measure.powermeter.kasa import KasaPowerMeter

            return KasaPowerMeter(spec.device_ip, credentials=self._kasa_credentials)
        if isinstance(spec, ManualPowerMeterSpec):
            return ManualPowerMeter()
        if isinstance(spec, MyStromPowerMeterSpec):
            return MyStromPowerMeter(spec.device_ip)
        if isinstance(spec, OcrPowerMeterSpec):
            return OcrPowerMeter()
        if isinstance(spec, ShellyPowerMeterSpec):
            return ShellyPowerMeter(
                spec.device_ip,
                spec.timeout,
                username=spec.username,
                password=self._shelly_password,
            )
        if isinstance(spec, TasmotaPowerMeterSpec):
            return TasmotaPowerMeter(spec.device_ip)
        if isinstance(spec, TuyaPowerMeterSpec):
            if self._tuya_device_key is None:
                raise PowerMeterError("Tuya device key is required")
            from measure.powermeter.tuya import TuyaPowerMeter

            return TuyaPowerMeter(spec.device_id, spec.device_ip, self._tuya_device_key, spec.version)
        if isinstance(spec, OwonOwh98xxPowerMeterSpec):
            from measure.powermeter.serial_scpi import OwonOwh98xxPowerMeter

            return OwonOwh98xxPowerMeter(spec.port, spec.baudrate, spec.timeout, spec.channel)
        assert_never(spec)  # pragma: no cover - all PowerMeterSpec variants handled

    def create_runner(
        self,
        request: MeasurementRequest,
        parameters: MeasurementParameters,
        sampler: PowerSampler,
    ) -> MeasurementRunner[Any]:
        interaction = self._interaction
        if isinstance(request, LightMeasurementRequest):
            light_controller = self.create_light_controller(request.controller)
            runner = LightRunner(
                sampler,
                parameters,
                light_controller,
                interaction,
                resume=request.resume_policy == ResumePolicy.RESUME,
            )
            runner.num_lights = request.multiple_light_count
            return runner
        if isinstance(request, SpeakerMeasurementRequest):
            media_controller = self._create_media_controller(request.controller)
            return SpeakerRunner(sampler, parameters, media_controller, interaction)
        if isinstance(request, RecorderMeasurementRequest):
            state_reader = self._create_recorder_state_reader() if request.recorded_entity_ids else None
            context = (
                build_recording_context(
                    request, HomeAssistantEntityCatalog(self._require_home_assistant()).load_snapshot().get_all()
                )
                if request.recorded_entity_ids
                else None
            )
            return RecorderRunner(sampler, interaction, state_reader, context)
        if isinstance(request, AverageMeasurementRequest):
            return AverageRunner(sampler, interaction=interaction)
        if isinstance(request, ChargingMeasurementRequest):
            charging_controller = self._create_charging_controller(request.controller)
            return ChargingRunner(
                sampler,
                parameters,
                charging_controller,
                interaction,
            )
        if isinstance(request, FanMeasurementRequest):
            fan_controller = self._create_fan_controller(request.controller)
            return FanRunner(sampler, parameters, fan_controller, interaction)
        assert_never(request)  # pragma: no cover - all MeasurementRequest variants handled

    def _create_recorder_state_reader(self) -> EntityStateReader:
        home_assistant = self._require_home_assistant()

        def read(entity_ids: Sequence[str]) -> Mapping[str, RecorderEntityState]:
            # One dump per sample. `get_state` has no single-entity WebSocket command
            # behind it, so asking per entity refetches every state in Home Assistant.
            wanted = set(entity_ids)
            return {
                state.entity_id: RecorderEntityState(state=str(state.state), attributes=state.attributes)
                for state in home_assistant.get_states()
                if state.entity_id in wanted
            }

        return read

    def create_light_controller(self, spec: LightControllerSpec) -> LightController:
        """Build a configured light controller for execution or active preflight checks."""

        if isinstance(spec, DummyLightControllerSpec):
            return DummyLightController()
        if isinstance(spec, HassLightControllerSpec | HassMultiLightControllerSpec):
            hass = self._require_home_assistant()
            return HassLightController(
                hass,
                spec.transition_time,
                entity_ids=spec.entity_ids,
                wait=self._interaction.wait,
            )
        if isinstance(spec, HueLightControllerSpec):
            from measure.controller.light.hue import HueLightController

            return HueLightController(spec.bridge_ip, light=spec.light)
        assert_never(spec)  # pragma: no cover - all LightControllerSpec variants handled

    def _create_media_controller(self, spec: MediaControllerSpec) -> MediaController:
        if isinstance(spec, DummyMediaControllerSpec):
            return DummyMediaController()
        if isinstance(spec, HassMediaControllerSpec):
            hass = self._require_home_assistant()
            return HassMediaController(hass, entity_id=spec.entity_id)
        assert_never(spec)  # pragma: no cover - all MediaControllerSpec variants handled

    def _create_charging_controller(self, spec: ChargingControllerSpec) -> ChargingController:
        if isinstance(spec, DummyChargingControllerSpec):
            return DummyChargingController()
        if isinstance(spec, HassChargingControllerSpec):
            hass = self._require_home_assistant()
            return HassChargingController(
                hass,
                entity_id=spec.entity_id,
            )
        assert_never(spec)  # pragma: no cover - all ChargingControllerSpec variants handled

    def _create_fan_controller(self, spec: FanControllerSpec) -> FanController:
        if isinstance(spec, DummyFanControllerSpec):
            return DummyFanController()
        if isinstance(spec, HassFanControllerSpec):
            hass = self._require_home_assistant()
            return HassFanController(hass, entity_id=spec.entity_id)
        assert_never(spec)  # pragma: no cover - all FanControllerSpec variants handled

    def _require_home_assistant(self) -> HomeAssistantManager:
        if self._home_assistant_manager is None:
            raise ValueError("Home Assistant runtime connection is required")
        return self._home_assistant_manager
