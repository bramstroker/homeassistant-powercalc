from __future__ import annotations

from contextvars import ContextVar
import logging
import re

from measure.assembler import MeasurementAssembler
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.execution import DummyLoadCalibrationStore, MeasurementExecution
from measure.ha_app.coordinator import SessionExecutionContext, SessionMeasurementService
from measure.ha_app.interaction import SessionInteraction
from measure.ha_app.session import SessionControl, SessionEventType, utc_now
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import MeasurementRequest
from measure.runner.runner import RunnerResult

_LOGGER = logging.getLogger("measure")
_SESSION_LOG_CONTROL: ContextVar[SessionControl | None] = ContextVar("measure_session_log_control", default=None)


class _SessionLogHandler(logging.Handler):
    def __init__(self, control: SessionControl, secrets: tuple[str, ...]) -> None:
        super().__init__(level=logging.INFO)
        self.control = control
        self.secrets = secrets

    def emit(self, record: logging.LogRecord) -> None:
        if _SESSION_LOG_CONTROL.get() is not self.control:
            return
        try:
            message = _redact(record.getMessage(), self.secrets)
            if record.levelno < logging.WARNING and message.startswith(("Changing light to:", "Measured power:")):
                return
            self.control.log(message, warning=record.levelno >= logging.WARNING)
        except Exception:  # noqa: BLE001  # pragma: no cover - logging must not break a measurement
            self.handleError(record)


class SessionDummyLoadCalibrationStore(DummyLoadCalibrationStore):
    """Persist calibration globally and inside the active session."""

    def __init__(self, storage: SessionStorage, session_id: str) -> None:
        self._storage = storage
        self._session_id = session_id

    def load(self, request: MeasurementRequest) -> DummyLoadCalibration | None:
        calibration = self._storage.load_session_dummy_load_calibration(self._session_id)
        if calibration is None:
            return None
        fingerprint = power_meter_fingerprint(request.power_meter)
        return calibration if calibration.power_meter_fingerprint == fingerprint else None

    def save(self, request: MeasurementRequest, resistance: float) -> DummyLoadCalibration:
        if request.dummy_load is None:
            raise ValueError("Cannot save calibration without dummy-load configuration")
        calibration = DummyLoadCalibration(
            description=request.dummy_load.description,
            resistance=resistance,
            calibrated_at=utc_now(),
            power_meter_fingerprint=power_meter_fingerprint(request.power_meter),
        )
        self._storage.save_session_dummy_load_calibration(self._session_id, calibration)
        self._storage.save_dummy_load_calibration(calibration)
        return calibration


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
        storage: SessionStorage | None = None,
    ) -> None:
        self.home_assistant = home_assistant
        self.storage = storage

    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        context: SessionExecutionContext,
    ) -> RunnerResult:
        """Run with session logging and redact secrets from surfaced failures."""

        handler = _SessionLogHandler(control, (self.home_assistant.token,))
        _LOGGER.addHandler(handler)
        context_token = _SESSION_LOG_CONTROL.set(control)
        try:
            return self._run(request, control, context)
        except Exception as error:
            message = _redact(str(error), (self.home_assistant.token,))
            if message != str(error):
                raise RuntimeError(message) from None
            raise
        finally:
            _SESSION_LOG_CONTROL.reset(context_token)
            _LOGGER.removeHandler(handler)

    def _run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        context: SessionExecutionContext,
    ) -> RunnerResult:
        control.checkpoint()
        if isinstance(request.power_meter, DummyPowerMeterSpec):
            _LOGGER.warning("Using synthetic test meter — reported power values are not real measurements")
        interaction = SessionInteraction(control)
        control.phase("Preparing measurement devices")
        calibration_store = (
            SessionDummyLoadCalibrationStore(self.storage, context.session_id)
            if request.dummy_load is not None and self.storage is not None
            else None
        )
        prepared = MeasurementAssembler(
            interaction,
            home_assistant=self.home_assistant,
            on_sample=control.sample,
            dummy_load_calibration_store=calibration_store,
        ).assemble(request)
        control.phase("Starting measurement")
        control.emit(SessionEventType.STATE, {"state": "running"})

        execution = MeasurementExecution(
            measurement=prepared,
            output_directory=context.artifact_directory,
        )
        return execution.run()
