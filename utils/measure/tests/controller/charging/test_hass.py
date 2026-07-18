from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant_api import State
from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.charging.const import ATTR_BATTERY_LEVEL
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.charging.hass import HassChargingController
from measure.controller.errors import ApiConnectionError
from measure.home_assistant import HomeAssistantEntityData, HomeAssistantManager
import pytest


def _entity(entity_id: str, state: str, **attributes: object) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=entity_id,
        state=SimpleNamespace(state=state, attributes=attributes),
    )


def _no_registry_data() -> HomeAssistantEntityData:
    """Entity data without a discoverable battery sensor."""
    return HomeAssistantEntityData(entities={}, entity_registry=[], device_registry=[])


def _battery_sensor_data(battery_state: str = "80") -> HomeAssistantEntityData:
    """Entity data where the charging device has a separate battery sensor on the same device."""
    return HomeAssistantEntityData(
        entities={
            "vacuum": SimpleNamespace(
                entities={"robot": _entity("vacuum.test", "docked", friendly_name="Robot")},
            ),
            "sensor": SimpleNamespace(
                entities={
                    "battery": _entity(
                        "sensor.test_battery_level",
                        battery_state,
                        friendly_name="Battery",
                        device_class="battery",
                        unit_of_measurement="%",
                    ),
                },
            ),
        },
        entity_registry=[
            SimpleNamespace(entity_id="vacuum.test", device_id="vacuum-device"),
            SimpleNamespace(entity_id="sensor.test_battery_level", device_id="vacuum-device"),
        ],
        device_registry=[{"id": "vacuum-device", "model": "Test Vacuum"}],
    )


def test_get_battery_level_from_sensor() -> None:
    """Battery level is read from a separate battery sensor on the same device."""
    client = _mock_client()
    client.get_entity_data.return_value = _battery_sensor_data(battery_state="80")
    client.get_entity.return_value = MagicMock(
        state=State(entity_id="sensor.test_battery_level", state="80", attributes={}),
    )
    assert _get_instance(client=client).get_battery_level() == 80
    client.get_entity.assert_called_once_with(entity_id="sensor.test_battery_level")


def test_get_battery_level_discovers_sensor_only_once() -> None:
    client = _mock_client()
    client.get_entity_data.return_value = _battery_sensor_data()
    client.get_entity.return_value = MagicMock(
        state=State(entity_id="sensor.test_battery_level", state="80", attributes={}),
    )
    controller = _get_instance(client=client)

    assert controller.get_battery_level() == 80
    assert controller.get_battery_level() == 80
    client.get_entity_data.assert_called_once_with()
    assert controller.battery_level_attribute is None


def test_cached_battery_sensor_failure_does_not_switch_to_attribute() -> None:
    client = _mock_client()
    client.get_entity_data.return_value = _battery_sensor_data()
    client.get_entity.side_effect = [
        MagicMock(state=State(entity_id="sensor.test_battery_level", state="80", attributes={})),
        MagicMock(state=State(entity_id="sensor.test_battery_level", state="unknown", attributes={})),
    ]
    controller = _get_instance(client=client)

    assert controller.get_battery_level() == 80
    with pytest.raises(BatteryLevelRetrievalError):
        controller.get_battery_level()

    client.get_entity_data.assert_called_once_with()
    assert [call.kwargs["entity_id"] for call in client.get_entity.call_args_list] == [
        "sensor.test_battery_level",
        "sensor.test_battery_level",
    ]


def test_get_battery_level_falls_back_to_attribute() -> None:
    """Without a battery sensor, the battery_level attribute of the main entity is used."""
    client = _mock_client()
    client.get_entity_data.return_value = _no_registry_data()
    client.get_entity.return_value = MagicMock(
        state=State(entity_id="vacuum.test", state="docked", attributes={ATTR_BATTERY_LEVEL: 75}),
    )
    controller = _get_instance(client=client)
    assert controller.get_battery_level() == 75
    assert controller.battery_level_attribute == ATTR_BATTERY_LEVEL


def test_get_battery_level_no_sensor_no_attribute_error() -> None:
    """Error when neither a battery sensor nor the attribute is available."""
    client = _mock_client()
    client.get_entity_data.return_value = _no_registry_data()
    client.get_entity.return_value = MagicMock(
        state=State(entity_id="vacuum.test", state="docked", attributes={}),
    )
    with pytest.raises(BatteryLevelRetrievalError):
        _get_instance(client=client).get_battery_level()


def test_get_battery_level_sensor_invalid_state() -> None:
    """Error when the discovered battery sensor state cannot be converted to int."""
    client = _mock_client()
    client.get_entity_data.return_value = _battery_sensor_data(battery_state="80")
    client.get_entity.return_value = MagicMock(
        state=State(entity_id="sensor.test_battery_level", state="unknown", attributes={}),
    )
    with pytest.raises(BatteryLevelRetrievalError):
        _get_instance(client=client).get_battery_level()


def test_is_charging() -> None:
    """Test checking if device is charging."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={},
    )

    client = _mock_client()
    client.get_entity.return_value = MagicMock(state=mocked_state)
    assert _get_instance(client=client).is_charging() is True


def test_is_not_charging() -> None:
    """Test checking if device is not charging."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="cleaning",
        attributes={},
    )

    client = _mock_client()
    client.get_entity.return_value = MagicMock(state=mocked_state)
    assert _get_instance(client=client).is_charging() is False


def test_is_valid_state() -> None:
    """Test checking if device is in a valid state."""
    for state in ["docked", "cleaning", "returning", "idle", "paused"]:
        mocked_state = State(
            entity_id="vacuum.test",
            state=state,
            attributes={},
        )

        client = _mock_client()
        client.get_entity.return_value = MagicMock(state=mocked_state)
        assert _get_instance(client=client).is_valid_state() is True


def test_is_invalid_state() -> None:
    """Test checking if device is in an invalid state."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="error",
        attributes={},
    )

    client = _mock_client()
    client.get_entity.return_value = MagicMock(state=mocked_state)
    assert _get_instance(client=client).is_valid_state() is False


def test_connection_validation() -> None:
    """Test API connection validation."""
    client = _mock_client()
    client.get_config.side_effect = HomeassistantAPIError("Error")
    with pytest.raises(ApiConnectionError):
        HassChargingController(client)


def _get_instance(*, client: MagicMock | None = None) -> HassChargingController:
    """Get a mocked instance of HassChargingController."""
    return HassChargingController(
        client or _mock_client(),
        entity_id="vacuum.test",
    )


def _mock_client() -> MagicMock:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_config.return_value = {}
    client.get_entity_data.return_value = _no_registry_data()
    return client
