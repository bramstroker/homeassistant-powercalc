from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from measure.home_assistant.client import HomeAssistantManager
from measure.powermeter.errors import PowerMeterError, UnsupportedFeatureError
from measure.powermeter.hass import HassPowerMeter
import pytest

UPDATED = datetime(2026, 9, 18, 10, tzinfo=UTC)


@pytest.mark.parametrize("include_voltage", [False, True])
@pytest.mark.parametrize("force_update", [False, True])
def test_power_reading_uses_source_timestamp_and_only_requested_sensors(
    include_voltage: bool, force_update: bool
) -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.side_effect = [
        SimpleNamespace(state="12.30", last_updated=UPDATED),
        SimpleNamespace(state="231.5"),
    ]
    wait = MagicMock()
    client.attach_mock(wait, "wait")
    meter = HassPowerMeter(
        client, force_update, entity_id="sensor.power", voltage_entity_id="sensor.voltage", wait=wait
    )

    reading = meter.get_power(include_voltage=include_voltage)

    assert reading.power == 12.3
    assert reading.updated == UPDATED.timestamp()
    assert reading.voltage == (231.5 if include_voltage else None)
    expected = []
    if force_update:
        expected.extend(
            [call.trigger_service("homeassistant", "update_entity", entity_id="sensor.power"), call.wait(1)]
        )
    expected.append(call.get_state(entity_id="sensor.power"))
    if include_voltage:
        expected.append(call.get_state(entity_id="sensor.voltage"))
    assert client.mock_calls == expected


def test_power_reading_falls_back_to_current_time_when_timestamp_is_missing() -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.return_value = SimpleNamespace(state="0", last_updated=None)
    meter = HassPowerMeter(client, False, entity_id="sensor.power")

    with patch("measure.powermeter.hass.time.time", return_value=1234):
        reading = meter.get_power()

    assert reading.power == 0
    assert reading.updated == 1234


@pytest.mark.parametrize("sensor", ["power", "voltage"])
@pytest.mark.parametrize("state", ["unavailable", "unknown", "not-a-number"])
def test_invalid_sensor_reading_is_not_returned_as_a_measurement(sensor: str, state: str) -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.side_effect = [
        SimpleNamespace(state=state if sensor == "power" else "12.3", last_updated=UPDATED),
        SimpleNamespace(state=state),
    ]
    meter = HassPowerMeter(client, False, entity_id="sensor.power", voltage_entity_id="sensor.voltage")
    expected_error = PowerMeterError if state == "unavailable" else ValueError

    with pytest.raises(expected_error):
        meter.get_power(include_voltage=True)

    assert client.get_state.call_count == (1 if sensor == "power" else 2)


def test_requesting_voltage_without_a_sensor_fails_explicitly() -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.return_value = SimpleNamespace(state="12.3", last_updated=UPDATED)
    meter = HassPowerMeter(client, False, entity_id="sensor.power")

    assert meter.has_voltage_support() is False
    client.get_state.assert_not_called()
    with pytest.raises(UnsupportedFeatureError, match="Voltage sensor entity not found"):
        meter.get_power(include_voltage=True)
    client.get_state.assert_called_once_with(entity_id="sensor.power")


@pytest.mark.parametrize("available", [False, True])
def test_voltage_support_checks_configured_sensor_availability(available: bool) -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.return_value = SimpleNamespace(state="230" if available else "unavailable")
    meter = HassPowerMeter(client, False, entity_id="sensor.power", voltage_entity_id="sensor.voltage")

    if available:
        assert meter.has_voltage_support() is True
    else:
        with pytest.raises(PowerMeterError, match=r"sensor\.voltage unavailable"):
            meter.has_voltage_support()
    client.get_state.assert_called_once_with(entity_id="sensor.voltage")


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
def test_diagnostic_sample_rejects_unavailable_sensor_without_forcing_update(state: str) -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.return_value = SimpleNamespace(state=state)
    wait = MagicMock()
    meter = HassPowerMeter(client, True, entity_id="sensor.power", wait=wait)

    with pytest.raises(PowerMeterError, match=f"sensor.power {state}"):
        meter.diagnostic_sample()
    client.trigger_service.assert_not_called()
    wait.assert_not_called()


@pytest.mark.parametrize("updated", [None, UPDATED])
def test_diagnostic_timestamp_falls_back_when_last_reported_is_missing(updated: datetime | None) -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_state.return_value = SimpleNamespace(state="12.30", last_reported=None, last_updated=updated)
    meter = HassPowerMeter(client, False, entity_id="sensor.power")

    with patch("measure.powermeter.hass.time.time", return_value=1234):
        reading = meter.diagnostic_sample()

    assert reading.power == 12.3
    assert reading.raw_value == "12.30"
    assert reading.reported_at == (updated.timestamp() if updated else 1234)
