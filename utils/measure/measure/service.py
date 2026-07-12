from __future__ import annotations

import logging
from pathlib import Path
import re

from measure.const import (
    QUESTION_ENTITY_ID,
    QUESTION_GENERATE_MODEL_JSON,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODEL_ID,
    QUESTION_MODEL_NAME,
)
from measure.controller.light.const import LutMode
from measure.controller.light.hass import HassLightController
from measure.model import write_model_json
from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID, QUESTION_VOLTAGEMETER_ENTITY_ID
from measure.powermeter.hass import HassPowerMeter
from measure.request import AppMeasureConfig, LightMeasurementRequest
from measure.runner.const import QUESTION_GZIP, QUESTION_MODE, QUESTION_MULTIPLE_LIGHTS, QUESTION_NUM_LIGHTS
from measure.runner.light import LightRunner
from measure.runner.runner import RunnerResult
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


def _redact(message: str, secrets: tuple[str, ...]) -> str:
    redacted = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+", r"\1[REDACTED]", message)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class MeasurementService:
    def __init__(self, hass_url: str, hass_token: str) -> None:
        self.hass_url = hass_url
        self.hass_token = hass_token

    def run(
        self,
        request: LightMeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        handler = _SessionLogHandler(control, (self.hass_token,))
        previous_level = _LOGGER.level
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
        request: LightMeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        control.checkpoint()
        config = AppMeasureConfig(request, self.hass_url, self.hass_token)
        power_meter = HassPowerMeter(config.hass_url, config.hass_token, config.hass_call_update_entity_service)
        light_controller = HassLightController(config.hass_url, config.hass_token, config.light_transition_time)
        answers: dict[str, object] = {
            QUESTION_ENTITY_ID: request.light_entity_id,
            QUESTION_POWERMETER_ENTITY_ID: request.power_entity_id,
            QUESTION_MODE: set(request.modes),
            QUESTION_GZIP: request.gzip,
            QUESTION_MULTIPLE_LIGHTS: request.num_lights > 1,
            QUESTION_NUM_LIGHTS: request.num_lights,
            QUESTION_GENERATE_MODEL_JSON: request.generate_model_json,
            QUESTION_MODEL_ID: request.model_id,
            QUESTION_MODEL_NAME: request.model_name,
            QUESTION_MEASURE_DEVICE: request.measure_device,
        }
        if request.voltage_entity_id:
            answers[QUESTION_VOLTAGEMETER_ENTITY_ID] = request.voltage_entity_id

        power_meter.process_answers(answers)
        voltage_enabled = power_meter.has_voltage_support()
        measure_util = MeasureUtil(
            power_meter,
            config,
            include_voltage=lambda: voltage_enabled,
            wait=control.wait,
        )
        runner = LightRunner(
            measure_util,
            config,
            light_controller=light_controller,
            session_control=control,
        )
        runner.prepare(answers)

        export_directory = output_root / request.model_id
        export_directory.mkdir(parents=True, exist_ok=True)
        control.emit(SessionEventType.STATE, {"state": "running"})
        try:
            result = runner.run(answers, str(export_directory))
            if result is None:
                raise RuntimeError("Measurement runner did not return a result")

            if request.generate_model_json:
                standby = runner.measure_standby_power()
                voltages = list(result.voltages or []) + standby.voltages
                write_model_json(
                    export_directory,
                    standby_power=standby.power,
                    name=request.model_name,
                    measure_device=request.measure_device,
                    config=config,
                    extra_json_data=result.model_json_data,
                    voltages=voltages,
                )
            return result, export_directory
        finally:
            try:
                light_controller.change_light_state(LutMode.BRIGHTNESS, on=False)
            except Exception as error:  # noqa: BLE001
                _LOGGER.warning("Could not turn off the light during session cleanup: %s", error)
