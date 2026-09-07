from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.powercalc.const import DATA_MEASURE_APP_COORDINATOR, DOMAIN
from custom_components.powercalc.measure import MEASURE_STATUS_EVENT, MEASURE_STATUS_TIMEOUT, MeasureAppCoordinator
from custom_components.powercalc.sensors.measure import MeasureSessionStatusSensor
from tests.common import async_advance_time, run_powercalc_setup


async def test_measure_sensor_is_only_created_after_app_announcement(hass: HomeAssistant) -> None:
    await run_powercalc_setup(hass)
    entity_registry = er.async_get(hass)

    assert hass.states.get("sensor.measure_session_status") is None
    assert entity_registry.async_get("measure_session_status") is None

    hass.bus.async_fire(
        MEASURE_STATUS_EVENT,
        {
            "app_version": "1.2.3",
            "state": "running",
            "session_id": "session-1",
            "error": None,
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.measure_session_status")
    assert state is not None
    assert state.state == "running"
    assert state.attributes["app_version"] == "1.2.3"
    assert state.attributes["session_id"] == "session-1"
    assert "controlled_entity" not in state.attributes


@pytest.mark.parametrize("controlled_entity", ["light.test", "light.one, light.two"])
async def test_measure_sensor_controlled_entity_is_retained_and_cleared(
    hass: HomeAssistant,
    controlled_entity: str,
) -> None:
    await run_powercalc_setup(hass)
    for session_state in ("running", "completed"):
        hass.bus.async_fire(
            MEASURE_STATUS_EVENT,
            {
                "app_version": "1.2.3",
                "state": session_state,
                "session_id": "session-1",
                "controlled_entity": controlled_entity,
            },
        )
        await hass.async_block_till_done()

        state = hass.states.get("sensor.measure_session_status")
        assert state is not None
        assert state.state == session_state
        assert state.attributes["controlled_entity"] == controlled_entity

    hass.bus.async_fire(
        MEASURE_STATUS_EVENT,
        {"app_version": "1.2.3", "state": "running", "session_id": "session-2", "controlled_entity": None},
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.measure_session_status")
    assert state is not None
    assert state.attributes["session_id"] == "session-2"
    assert "controlled_entity" not in state.attributes


@pytest.mark.parametrize("controlled_entity", [123, ["light.test"], {"entity_id": "light.test"}])
def test_measure_status_rejects_invalid_controlled_entity(hass: HomeAssistant, controlled_entity: object) -> None:
    coordinator = MeasureAppCoordinator(hass, {})

    assert not coordinator.async_process_event(
        {"app_version": "1.2.3", "state": "running", "controlled_entity": controlled_entity},
    )
    assert coordinator.data is None
    assert not coordinator.available


async def test_measure_sensor_updates_and_becomes_unavailable_without_heartbeat(hass: HomeAssistant) -> None:
    await run_powercalc_setup(hass)
    hass.bus.async_fire(
        MEASURE_STATUS_EVENT,
        {
            "app_version": "1.2.3",
            "state": "running",
            "session_id": "session-1",
            "error": None,
        },
    )
    await hass.async_block_till_done()

    hass.bus.async_fire(
        MEASURE_STATUS_EVENT,
        {
            "app_version": "1.2.3",
            "state": "failed",
            "session_id": "session-1",
            "error": "Meter disconnected",
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.measure_session_status")
    assert state is not None
    assert state.state == "failed"
    assert state.attributes["error"] == "Meter disconnected"

    await async_advance_time(hass, MEASURE_STATUS_TIMEOUT + 1)

    state = hass.states.get("sensor.measure_session_status")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_invalid_measure_announcement_does_not_create_sensor(hass: HomeAssistant) -> None:
    await run_powercalc_setup(hass)

    hass.bus.async_fire(
        MEASURE_STATUS_EVENT,
        {"app_version": "1.2.3", "state": "not-a-session-state"},
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.measure_session_status") is None


async def test_measure_sensor_creation_can_retry_after_platform_load_failure(hass: HomeAssistant) -> None:
    await run_powercalc_setup(hass)
    coordinator: MeasureAppCoordinator = hass.data[DOMAIN][DATA_MEASURE_APP_COORDINATOR]
    event = Event(
        MEASURE_STATUS_EVENT,
        {"app_version": "1.2.3", "state": "idle"},
    )
    load_platform = AsyncMock(side_effect=[RuntimeError("Platform load failed"), None])

    with patch(
        "custom_components.powercalc.measure.async_load_platform",
        load_platform,
    ):
        with pytest.raises(RuntimeError, match="Platform load failed"):
            await coordinator.async_handle_app_status_event(event)

        assert coordinator.entity_creation_started is False

        await coordinator.async_handle_app_status_event(event)

    assert coordinator.entity_creation_started is True
    assert load_platform.await_count == 2
    coordinator.async_shutdown()


def test_measure_sensor_without_snapshot_and_listener_unsubscribe(hass: HomeAssistant) -> None:
    coordinator = MeasureAppCoordinator(hass, {})
    sensor = MeasureSessionStatusSensor(coordinator)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    listener = Mock()
    unsubscribe = coordinator.async_add_listener(listener)
    unsubscribe()
    coordinator.async_process_event({"app_version": "1.2.3", "state": "idle"})

    listener.assert_not_called()
    coordinator.async_shutdown()
