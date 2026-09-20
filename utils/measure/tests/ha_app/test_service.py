import logging
from pathlib import Path
from threading import Barrier, Thread
from unittest.mock import MagicMock, patch

from measure.controller.light.dummy import DummyLightController
from measure.controller.light.spec import HassLightControllerSpec
from measure.ha_app.coordinator import SessionExecutionContext
from measure.ha_app.service import MeasurementService, SessionDummyLoadCalibrationStore, _redact_secrets
from measure.ha_app.session import (
    SessionControl,
    SessionEvent,
    SessionEventType,
    SessionSnapshot,
    SessionState,
    utc_now,
)
from measure.ha_app.storage import SessionStorage
from measure.home_assistant.client import HomeAssistantManager
from measure.powermeter.credentials import TapoCredentials
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec
from measure.request import AverageMeasurementRequest, DummyLoadCalibrationRequest, LightMeasurementRequest
from measure.runner.runner import RunnerResult
from measure.tuning import MeasurementParameters
import pytest


def test_service_runs_light_measurement_without_terminal(tmp_path: Path) -> None:
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(entity_id="sensor.test_power"),
        generate_model=False,
        gzip=False,
        parameters=MeasurementParameters(sleep_time=0, sleep_initial=0, bri_bri_steps=255),
    )
    progress: list[SessionEvent] = []
    control = SessionControl()
    control.subscribe(progress.append)
    logger = logging.getLogger("measure")
    previous_level = logger.level
    previous_handlers = list(logger.handlers)
    logger.setLevel(logging.INFO)

    try:
        with (
            patch("measure.assembler.HassPowerMeter", return_value=DummyPowerMeter()),
            patch("measure.assembler.HassLightController", return_value=DummyLightController()),
        ):
            result = MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token")).run(
                request,
                control,
                SessionExecutionContext(
                    session_id="explicit-session",
                    artifact_directory=tmp_path / "custom-artifacts",
                ),
            )
        assert logger.level == logging.INFO
        assert logger.handlers == previous_handlers
    finally:
        logger.setLevel(previous_level)

    assert result.model_json_data["device_type"] == "light"
    assert (tmp_path / "custom-artifacts" / "brightness.csv").is_file()
    progress_events = [event for event in progress if event.type == SessionEventType.PROGRESS]
    assert progress_events[-1].data["completed"] == progress_events[-1].data["total"]
    phases = [event.data["message"] for event in progress if event.type == SessionEventType.PHASE]
    assert phases[:2] == ["Preparing measurement devices", "Starting measurement"]
    assert any(message.startswith("Stabilizing light") for message in phases)
    assert any(event.type == SessionEventType.LOG for event in progress)


def test_sensitive_values_are_redacted_from_session_messages() -> None:
    redacted = _redact_secrets("Authorization: Bearer secret-token", ("secret-token",))

    assert redacted == "Authorization: Bearer [REDACTED]"


def test_service_uses_explicit_session_id_for_dummy_load_storage(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path / "storage")
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(
            entity_id="sensor.test_power",
            voltage_entity_id="sensor.test_voltage",
        ),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )
    context = SessionExecutionContext(
        session_id="explicit-session-id",
        artifact_directory=tmp_path / "unrelated" / "artifacts",
    )

    with (
        patch("measure.ha_app.service.SessionDummyLoadCalibrationStore") as calibration_store,
        patch("measure.ha_app.service.MeasurementAssembler") as assembler,
        patch("measure.ha_app.service.MeasurementExecution") as execution,
    ):
        assembler.return_value.assemble.return_value = MagicMock()
        execution.return_value.run.return_value = RunnerResult(model_json_data={})
        MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token"), storage).run(
            request,
            SessionControl(),
            context,
        )

    calibration_store.assert_called_once_with(storage, "explicit-session-id")


def test_service_preserves_logger_configuration_and_redacts_failure(tmp_path: Path) -> None:
    logger = logging.getLogger("measure")
    previous_level = logger.level
    previous_handlers = list(logger.handlers)
    logger.setLevel(logging.WARNING)
    service = MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "secret-token"))

    def fail(*_: object) -> RunnerResult:
        assert logger.level == logging.WARNING
        raise RuntimeError("Authorization: Bearer secret-token")

    request = MagicMock()
    session_control = SessionControl()
    execution_context = SessionExecutionContext(session_id="failed-session", artifact_directory=tmp_path)

    try:
        with (
            patch.object(service, "_run", side_effect=fail),
            pytest.raises(RuntimeError, match=r"Authorization: Bearer \[REDACTED\]"),
        ):
            service.run(request, session_control, execution_context)

        assert logger.level == logging.WARNING
        assert logger.handlers == previous_handlers
    finally:
        logger.setLevel(previous_level)


def test_service_redacts_tapo_credentials_from_logs_and_failures(tmp_path: Path) -> None:
    credentials = TapoCredentials(username="user@example.com", password="account-password")  # noqa: S106
    service = MeasurementService(
        HomeAssistantManager("ws://supervisor/core/websocket", "ha-token"),
        kasa_credentials=credentials,
    )
    events: list[SessionEvent] = []
    control = SessionControl()
    control.subscribe(events.append)
    message = f"Authentication failed for {credentials.username}: {credentials.password}"

    def fail(*_: object) -> RunnerResult:
        logging.getLogger("measure").warning(message)
        raise RuntimeError(message)

    with (
        patch.object(service, "_run", side_effect=fail),
        pytest.raises(RuntimeError) as error,
    ):
        service.run(MagicMock(), control, SessionExecutionContext(session_id="test", artifact_directory=tmp_path))

    expected = "Authentication failed for [REDACTED]: [REDACTED]"
    assert str(error.value) == expected
    assert [event.data["message"] for event in events if event.type == SessionEventType.WARNING] == [expected]


def test_concurrent_services_capture_only_their_own_log_context(tmp_path: Path) -> None:
    logger = logging.getLogger("measure")
    previous_level = logger.level
    previous_handlers = list(logger.handlers)
    logger.setLevel(logging.INFO)
    controls = (SessionControl(), SessionControl())
    events: tuple[list[SessionEvent], list[SessionEvent]] = ([], [])
    for control, session_events in zip(controls, events, strict=True):
        control.subscribe(session_events.append)
    services = (
        MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token-a")),
        MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token-b")),
    )
    barrier = Barrier(2)

    def run(message: str) -> RunnerResult:
        barrier.wait()
        logger.info(message)
        return MagicMock(spec=RunnerResult)

    try:
        with (
            patch.object(services[0], "_run", side_effect=lambda *_: run("Session A")),
            patch.object(services[1], "_run", side_effect=lambda *_: run("Session B")),
        ):
            threads = [
                Thread(
                    target=service.run,
                    args=(
                        MagicMock(),
                        control,
                        SessionExecutionContext(
                            session_id=f"concurrent-{index}",
                            artifact_directory=tmp_path / f"concurrent-{index}",
                        ),
                    ),
                )
                for index, (service, control) in enumerate(zip(services, controls, strict=True))
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        messages = [
            [event.data["message"] for event in session_events if event.type == SessionEventType.LOG]
            for session_events in events
        ]
        assert messages == [["Session A"], ["Session B"]]
        assert logger.level == logging.INFO
        assert logger.handlers == previous_handlers
    finally:
        logger.setLevel(previous_level)


def test_session_dummy_load_store_persists_for_resume_and_future_sessions(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    now = utc_now()
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(
            entity_id="sensor.test_power",
            voltage_entity_id="sensor.test_voltage",
        ),
        dummy_load=DummyLoadCalibrationRequest(description="40 W incandescent bulb"),
    )
    storage.create(
        SessionSnapshot(id="a1b2-c3d4", state=SessionState.RUNNING, created_at=now, updated_at=now),
        request,
    )
    store = SessionDummyLoadCalibrationStore(storage, "a1b2-c3d4")

    calibration = store.save(request, 1322.5)

    assert store.load(request) == calibration
    assert storage.load_dummy_load_calibration() == calibration


def test_session_calibration_is_only_reused_for_the_same_meter(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    request = AverageMeasurementRequest(
        power_meter=HassPowerMeterSpec(entity_id="sensor.power"),
        dummy_load=DummyLoadCalibrationRequest(description="Calibration bulb"),
    )
    now = utc_now()
    storage.create(
        SessionSnapshot(id="calibration", state=SessionState.RUNNING, created_at=now, updated_at=now),
        request,
    )
    store = SessionDummyLoadCalibrationStore(storage, "calibration")

    assert store.load(request) is None
    calibration = store.save(request, 1322.5)
    other_request = request.model_copy(update={"power_meter": HassPowerMeterSpec(entity_id="sensor.other_power")})

    assert store.load(other_request) is None
    assert store.load(request) == calibration
    assert storage.load_dummy_load_calibration() == calibration


def test_session_calibration_requires_dummy_load_configuration(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    store = SessionDummyLoadCalibrationStore(storage, "calibration")
    request = AverageMeasurementRequest(power_meter=DummyPowerMeterSpec())

    with pytest.raises(ValueError, match="without dummy-load configuration"):
        store.save(request, 1322.5)

    assert storage.load_dummy_load_calibration() is None


def test_service_preserves_non_secret_failure_and_removes_session_logging(tmp_path: Path) -> None:
    service = MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "secret-token"))
    control = SessionControl()
    events: list[SessionEvent] = []
    control.subscribe(events.append)
    logger = logging.getLogger("measure")
    previous_handlers = list(logger.handlers)
    failure = OSError("Meter disconnected")

    with (
        patch.object(service, "_run", side_effect=failure),
        pytest.raises(OSError, match="Meter disconnected") as error,
    ):
        service.run(
            AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()),
            control,
            SessionExecutionContext(session_id="failed", artifact_directory=tmp_path),
        )

    assert error.value is failure
    assert logger.handlers == previous_handlers
    logger.warning("Unrelated log after measurement")
    assert events == []


def test_service_warns_when_using_synthetic_measurements(tmp_path: Path) -> None:
    service = MeasurementService(HomeAssistantManager("ws://supervisor/core/websocket", "token"))
    control = SessionControl()
    events: list[SessionEvent] = []
    control.subscribe(events.append)
    result = RunnerResult(model_json_data={})

    with (
        patch("measure.ha_app.service.MeasurementAssembler"),
        patch("measure.ha_app.service.MeasurementExecution") as execution,
    ):
        execution.return_value.run.return_value = result
        actual = service.run(
            AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()),
            control,
            SessionExecutionContext(session_id="synthetic", artifact_directory=tmp_path),
        )

    assert actual is result
    assert [event.data["message"] for event in events if event.type == SessionEventType.WARNING] == [
        "Using synthetic test meter — reported power values are not real measurements",
    ]
    assert [event.data for event in events if event.type == SessionEventType.STATE] == [{"state": "running"}]
