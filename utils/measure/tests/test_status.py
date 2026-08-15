import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock

from measure.const import HASS_EVENT_MEASURE_STATUS
from measure.controller.light.spec import DummyLightControllerSpec
from measure.ha_app.coordinator import MeasurementCoordinator
from measure.ha_app.session import SessionSnapshot, SessionState
from measure.ha_app.status import MeasureStatusPublisher
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import LightMeasurementRequest
from measure.version import measure_version
import pytest


def light_request() -> LightMeasurementRequest:
    return LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
    )


def test_status_publisher_announces_idle_app(tmp_path: Path) -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    coordinator = MeasurementCoordinator(SessionStorage(tmp_path), MagicMock())
    publisher = MeasureStatusPublisher(home_assistant, coordinator)

    publisher._publish()  # noqa: SLF001

    home_assistant.fire_event.assert_called_once_with(
        HASS_EVENT_MEASURE_STATUS,
        app_version=measure_version(),
        state=SessionState.IDLE,
        session_id=None,
        error=None,
    )


def test_status_publisher_announces_retained_session(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    snapshot = SessionSnapshot(
        id="failed-session",
        state=SessionState.FAILED,
        created_at="2026-08-15T12:00:00Z",
        updated_at="2026-08-15T12:01:00Z",
        error="Meter disconnected",
    )
    storage.create(snapshot, light_request())
    home_assistant = MagicMock(spec=HomeAssistantManager)
    publisher = MeasureStatusPublisher(home_assistant, MeasurementCoordinator(storage, MagicMock()))

    publisher._publish()  # noqa: SLF001

    home_assistant.fire_event.assert_called_once_with(
        HASS_EVENT_MEASURE_STATUS,
        app_version=measure_version(),
        state=SessionState.FAILED,
        session_id="failed-session",
        error="Meter disconnected",
    )


def test_status_publisher_lifecycle_and_error_recovery(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def exercise() -> None:
        home_assistant = MagicMock(spec=HomeAssistantManager)
        home_assistant.fire_event.side_effect = RuntimeError("Home Assistant unavailable")
        coordinator = MeasurementCoordinator(SessionStorage(tmp_path), MagicMock())
        publisher = MeasureStatusPublisher(home_assistant, coordinator, heartbeat_interval=3600)

        await publisher.async_start()
        for _ in range(100):
            if home_assistant.fire_event.call_count == 1:
                break
            await asyncio.sleep(0.005)

        home_assistant.fire_event.side_effect = None
        publisher._signal_changed()  # noqa: SLF001
        for _ in range(100):
            if home_assistant.fire_event.call_count == 2:
                break
            await asyncio.sleep(0.005)

        await publisher.async_stop()
        publisher._signal_changed()  # noqa: SLF001
        assert home_assistant.fire_event.call_count == 2

    with caplog.at_level(logging.WARNING, logger="measure"):
        asyncio.run(exercise())

    assert "Could not publish Measure status to Home Assistant" in caplog.text
