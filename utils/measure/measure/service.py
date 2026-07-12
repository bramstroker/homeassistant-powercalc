from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path
import re

from measure.const import (
    QUESTION_ENTITY_ID,
    QUESTION_GENERATE_MODEL_JSON,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODEL_ID,
    QUESTION_MODEL_NAME,
    MeasureType,
)
from measure.controller.light.const import LutMode
from measure.controller.light.hass import HassLightController
from measure.execution import MeasurementExecution, MeasurementMetadata
from measure.interactions import SessionInteraction
from measure.model import write_model_json
from measure.powermeter.const import (
    QUESTION_POWERMETER_ENTITY_ID,
    QUESTION_VOLTAGEMETER_ENTITY_ID,
    PowerMeterType,
)
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.hass import HassPowerMeter
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.powermeter.shelly import ShellyPowerMeter
from measure.request import AppMeasureConfig, LightMeasurementRequest, MeasurementRunRequest
from measure.runner.average import AverageRunner
from measure.runner.charging import ChargingRunner
from measure.runner.const import QUESTION_GZIP, QUESTION_MODE, QUESTION_MULTIPLE_LIGHTS, QUESTION_NUM_LIGHTS
from measure.runner.fan import FanRunner
from measure.runner.light import LightRunner
from measure.runner.recorder import RecorderRunner
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.runner.speaker import SpeakerRunner
from measure.session import SessionControl, SessionEventType
from measure.util.measure_util import MeasureUtil

_LOGGER = logging.getLogger("measure")


class _SessionLogHandler(logging.Handler):
    def __init__(self, control: SessionControl, secrets: tuple[str, ...]) -> None:
        super().__init__(level=logging.INFO)
        self.control = control
        self.secrets = secrets

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = _redact(record.getMessage(), self.secrets)
            if record.levelno < logging.WARNING and message.startswith(("Changing light to:", "Measured power:")):
                return
            self.control.log(message, warning=record.levelno >= logging.WARNING)
        except Exception:  # noqa: BLE001  # pragma: no cover - logging must not break a measurement
            self.handleError(record)


class _SamplingPowerMeter(PowerMeter):
    """Wraps a power meter to stream every reading to the session as a live sample."""

    def __init__(self, inner: PowerMeter, on_sample: Callable[[float], None]) -> None:
        self._inner = inner
        self._on_sample = on_sample

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        result = self._inner.get_power(include_voltage=include_voltage)
        try:
            self._on_sample(result.power)
        except Exception:  # noqa: BLE001  # pragma: no cover - streaming must not break a measurement
            _LOGGER.debug("Failed to emit live power sample", exc_info=True)
        return result

    def has_voltage_support(self) -> bool:
        return self._inner.has_voltage_support()

    def process_answers(self, answers: dict[str, object]) -> None:
        self._inner.process_answers(answers)


def _redact(message: str, secrets: tuple[str, ...]) -> str:
    redacted = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+", r"\1[REDACTED]", message)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class MeasurementService:
    def __init__(
        self,
        hass_url: str,
        hass_token: str,
        power_meter: PowerMeterType = PowerMeterType.HASS,
        shelly_ip: str | None = None,
    ) -> None:
        self.hass_url = hass_url
        self.hass_token = hass_token
        self.power_meter = power_meter
        self.shelly_ip = shelly_ip

    def run(
        self,
        request: LightMeasurementRequest | MeasurementRunRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        handler = _SessionLogHandler(control, (self.hass_token,))
        previous_level = _LOGGER.level
        # Ensure at least INFO reaches the handler, but preserve DEBUG when enabled.
        if previous_level == logging.NOTSET or previous_level > logging.INFO:
            _LOGGER.setLevel(logging.INFO)
        _LOGGER.addHandler(handler)
        try:
            return self._run(request, control, output_root)
        except Exception as error:
            message = _redact(str(error), (self.hass_token,))
            if message != str(error):
                raise RuntimeError(message) from None
            raise
        finally:
            _LOGGER.removeHandler(handler)
            _LOGGER.setLevel(previous_level)

    def _run(
        self,
        request: LightMeasurementRequest | MeasurementRunRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        control.checkpoint()
        config = AppMeasureConfig(request, self.hass_url, self.hass_token, self.power_meter)
        power_meter: PowerMeter
        if config.selected_power_meter == PowerMeterType.DUMMY:
            _LOGGER.warning("Using dummy power meter — reported power values are synthetic, not real measurements")
            power_meter = DummyPowerMeter()
        elif config.selected_power_meter == PowerMeterType.SHELLY:
            if not self.shelly_ip:
                raise RuntimeError("Shelly IP must be configured before starting a measurement")
            power_meter = ShellyPowerMeter(self.shelly_ip)
        else:
            power_meter = HassPowerMeter(config.hass_url, config.hass_token, config.hass_call_update_entity_service)
        power_meter = _SamplingPowerMeter(power_meter, control.sample)
        light_controller = HassLightController(config.hass_url, config.hass_token, config.light_transition_time)
        answers = self._answers(request)

        power_meter.process_answers(answers)
        voltage_enabled = power_meter.has_voltage_support()
        measure_util = MeasureUtil(
            power_meter,
            config,
            include_voltage=lambda: voltage_enabled,
            wait=control.wait,
        )
        runner, cleanup = self._runner(request, measure_util, config, light_controller, control)
        export_directory = output_root / request.model_id
        control.emit(SessionEventType.STATE, {"state": "running"})

        def write_model(
            directory: Path,
            standby_power: float,
            name: str,
            measure_device: str,
            extra_json_data: dict[str, object],
            voltages: list[float],
        ) -> None:
            self._write_model(config, directory, standby_power, name, measure_device, extra_json_data, voltages)

        execution = MeasurementExecution(
            runner=runner,
            measure_util=measure_util,
            answers=answers,
            metadata=MeasurementMetadata(
                model_id=request.model_id,
                model_name=request.model_name,
                measure_device=request.measure_device,
                generate_model_json=request.generate_model_json,
            ),
            output_directory=export_directory,
            interaction=SessionInteraction(control),
            write_model=write_model,
            cleanup=cleanup,
        )
        outcome = execution.run()
        return outcome.runner_result, outcome.export_directory or export_directory

    @staticmethod
    def _write_model(
        config: AppMeasureConfig,
        directory: Path,
        standby_power: float,
        name: str,
        measure_device: str,
        extra_json_data: dict[str, object],
        voltages: list[float],
    ) -> None:
        write_model_json(
            directory,
            standby_power=standby_power,
            name=name,
            measure_device=measure_device,
            config=config,
            extra_json_data=extra_json_data,
            voltages=voltages,
        )

    @staticmethod
    def _answers(request: LightMeasurementRequest | MeasurementRunRequest) -> dict[str, object]:
        if isinstance(request, MeasurementRunRequest):
            return dict(request.answers)
        answers: dict[str, object] = {
            QUESTION_ENTITY_ID: request.light_entity_id,
            QUESTION_MODE: set(request.modes),
            QUESTION_GZIP: request.gzip,
            QUESTION_MULTIPLE_LIGHTS: request.num_lights > 1,
            QUESTION_NUM_LIGHTS: request.num_lights,
            QUESTION_GENERATE_MODEL_JSON: request.generate_model_json,
            QUESTION_MODEL_ID: request.model_id,
            QUESTION_MODEL_NAME: request.model_name,
            QUESTION_MEASURE_DEVICE: request.measure_device,
        }
        if request.power_entity_id:
            answers[QUESTION_POWERMETER_ENTITY_ID] = request.power_entity_id
        if request.voltage_entity_id:
            answers[QUESTION_VOLTAGEMETER_ENTITY_ID] = request.voltage_entity_id
        return answers

    @staticmethod
    def _runner(
        request: LightMeasurementRequest | MeasurementRunRequest,
        measure_util: MeasureUtil,
        config: AppMeasureConfig,
        light_controller: HassLightController,
        control: SessionControl,
    ) -> tuple[MeasurementRunner, Callable[[], None] | None]:
        measure_type = MeasureType.LIGHT if isinstance(request, LightMeasurementRequest) else request.measure_type
        interaction = SessionInteraction(control)
        if measure_type == MeasureType.LIGHT:
            return (
                LightRunner(measure_util, config, light_controller=light_controller, session_control=control),
                lambda: MeasurementService._turn_off_light(light_controller),
            )
        if measure_type == MeasureType.SPEAKER:
            return SpeakerRunner(measure_util, config, interaction), None
        if measure_type == MeasureType.RECORDER:
            return RecorderRunner(measure_util, config, interaction), None
        if measure_type == MeasureType.AVERAGE:
            return AverageRunner(measure_util, interaction=interaction), None
        if measure_type == MeasureType.CHARGING:
            return ChargingRunner(measure_util, config, interaction), None
        if measure_type == MeasureType.FAN:
            return FanRunner(measure_util, config, interaction), None
        raise RuntimeError(f"Unsupported measure type: {measure_type}")

    @staticmethod
    def _turn_off_light(light_controller: HassLightController) -> None:
        try:
            light_controller.change_light_state(LutMode.BRIGHTNESS, on=False)
        except Exception as error:  # noqa: BLE001
            _LOGGER.warning("Could not turn off the light during session cleanup: %s", error)
