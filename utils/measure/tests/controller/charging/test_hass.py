from unittest.mock import MagicMock

from homeassistant_api import State
from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.charging.const import ATTR_BATTERY_LEVEL, BatteryLevelSourceType
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.charging.hass import HassChargingController
from measure.controller.errors import ApiConnectionError
from measure.home_assistant import HomeAssistantManager
import pytest


def test_get_battery_level_attribute() -> None:
    """Test retrieving battery level from an attribute."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={ATTR_BATTERY_LEVEL: 75},
    )

    client = _mock_client()
    client.get_entity.return_value = MagicMock(state=mocked_state)
    hass_controller = _get_instance(client=client, battery_level_attribute=ATTR_BATTERY_LEVEL)
    assert hass_controller.get_battery_level() == 75


def test_get_battery_level_entity() -> None:
    """Test retrieving battery level from a separate entity."""
    mocked_entity = MagicMock()
    mocked_entity.state = State(
        entity_id="sensor.vacuum_battery",
        state="80",
        attributes={},
    )

    client = _mock_client()
    client.get_entity.return_value = mocked_entity
    hass_controller = _get_instance(
        client=client,
        battery_level_source_type=BatteryLevelSourceType.ENTITY,
        battery_level_entity_id="sensor.vacuum_battery",
    )
    assert hass_controller.get_battery_level() == 80


def test_get_battery_level_attribute_error() -> None:
    """Test error when attribute is missing."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={},
    )

    client = _mock_client()
    client.get_entity.return_value = MagicMock(state=mocked_state)
    hass_controller = _get_instance(client=client, battery_level_attribute=ATTR_BATTERY_LEVEL)
    with pytest.raises(BatteryLevelRetrievalError):
        hass_controller.get_battery_level()


def test_get_battery_level_entity_error() -> None:
    """Test error when entity is not found."""
    client = _mock_client()
    client.get_entity.return_value = None
    hass_controller = _get_instance(
        client=client,
        battery_level_source_type=BatteryLevelSourceType.ENTITY,
        battery_level_entity_id="sensor.vacuum_battery",
    )
    with pytest.raises(BatteryLevelRetrievalError):
        hass_controller.get_battery_level()


def test_get_battery_level_entity_invalid_state() -> None:
    """Test error when entity state cannot be converted to int."""
    mocked_entity = MagicMock()
    mocked_entity.state = State(
        entity_id="sensor.vacuum_battery",
        state="unknown",
        attributes={},
    )

    client = _mock_client()
    client.get_entity.return_value = mocked_entity
    hass_controller = _get_instance(
        client=client,
        battery_level_source_type=BatteryLevelSourceType.ENTITY,
        battery_level_entity_id="sensor.vacuum_battery",
    )
    with pytest.raises(BatteryLevelRetrievalError):
        hass_controller.get_battery_level()


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


def _get_instance(
    *,
    client: MagicMock | None = None,
    battery_level_source_type: BatteryLevelSourceType = BatteryLevelSourceType.ATTRIBUTE,
    battery_level_attribute: str | None = None,
    battery_level_entity_id: str | None = None,
) -> HassChargingController:
    """Get a mocked instance of HassChargingController."""
    return HassChargingController(
        client or _mock_client(),
        entity_id="vacuum.test",
        battery_level_source_type=battery_level_source_type,
        battery_level_attribute=battery_level_attribute,
        battery_level_entity_id=battery_level_entity_id,
    )


def _mock_client() -> MagicMock:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_config.return_value = {}
    return client
