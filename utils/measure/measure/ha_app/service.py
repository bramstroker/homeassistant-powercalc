from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path
import re

from measure.assembler import MeasurementAssembler
from measure.execution import MeasurementExecution
from measure.ha_app.coordinator import SessionMeasurementService
from measure.ha_app.interaction import SessionInteraction
from measure.ha_app.session import SessionControl, SessionEventType
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import MeasurementRequest
from measure.runner.runner import RunnerResult

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


def _redact(message: str, secrets: tuple[str, ...]) -> str:
    redacted = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+", r"\1[REDACTED]", message)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class MeasurementService(SessionMeasurementService):
    """Compose Home Assistant adapters and execute one measurement session."""

    def __init__(
        self,
        home_assistant: HomeAssistantManager,
    ) -> None:
        self.home_assistant = home_assistant

    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        """Run with session logging and redact secrets from surfaced failures."""

        handler = _SessionLogHandler(control, (self.home_assistant.token,))
        previous_level = _LOGGER.level
        # Ensure at least INFO reaches the handler, but preserve DEBUG when enabled.
        if previous_level == logging.NOTSET or previous_level > logging.INFO:
            _LOGGER.setLevel(logging.INFO)
        _LOGGER.addHandler(handler)
        try:
            return self._run(request, control, output_root)
        except Exception as error:
            message = _redact(str(error), (self.home_assistant.token,))
            if message != str(error):
                raise RuntimeError(message) from None
            raise
        finally:
            _LOGGER.removeHandler(handler)
            _LOGGER.setLevel(previous_level)

    def _run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        control.checkpoint()
        if isinstance(request.power_meter, DummyPowerMeterSpec):
            _LOGGER.warning("Using dummy power meter — reported power values are synthetic, not real measurements")
        interaction = SessionInteraction(control)
        control.phase("Preparing measurement devices")
        prepared = MeasurementAssembler(
            interaction,
            home_assistant=self.home_assistant,
            power_meter_decorator=lambda meter: _SamplingPowerMeter(meter, control.sample),
        ).assemble(request)
        output_directory = output_root / request.model_id
        control.phase("Starting measurement")
        control.emit(SessionEventType.STATE, {"state": "running"})

        execution = MeasurementExecution(
            measurement=prepared,
            output_directory=output_directory,
        )
        return execution.run()
