from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant_api import State
from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.charging.const import ATTR_BATTERY_LEVEL
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.charging.hass import HassChargingController
from measure.controller.errors import ApiConnectionError, ControllerError
from measure.home_assistant.client import HomeAssistantEntityData
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
            SimpleNamespace(entity_id="vacuum.test", device_id="vacuum-device", platform="roborock"),
            SimpleNamespace(entity_id="sensor.test_battery_level", device_id="vacuum-device", platform="roborock"),
        ],
        device_registry=[{"id": "vacuum-device", "model": "Test Vacuum"}],
    )


@pytest.fixture
def charging_hass_client(hass_client: MagicMock) -> MagicMock:
    hass_client.get_entity_data.return_value = _no_registry_data()
    return hass_client


def test_get_battery_level_from_sensor(charging_hass_client: MagicMock) -> None:
    """Battery level is read from a separate battery sensor on the same device."""
    charging_hass_client.get_entity_data.return_value = _battery_sensor_data(battery_state="80")
    charging_hass_client.get_entity.return_value = MagicMock(
        state=State(entity_id="sensor.test_battery_level", state="80", attributes={}),
    )
    assert _get_instance(charging_hass_client).get_battery_level() == 80
    charging_hass_client.get_entity.assert_called_once_with(entity_id="sensor.test_battery_level")


def test_get_battery_level_discovers_sensor_only_once(charging_hass_client: MagicMock) -> None:
    charging_hass_client.get_entity_data.return_value = _battery_sensor_data()
    charging_hass_client.get_entity.return_value = MagicMock(
        state=State(entity_id="sensor.test_battery_level", state="80", attributes={}),
    )
    controller = _get_instance(charging_hass_client)

    assert controller.get_battery_level() == 80
    assert controller.get_battery_level() == 80
    charging_hass_client.get_entity_data.assert_called_once_with()
    assert controller.battery_level_attribute is None


def test_cached_battery_sensor_failure_does_not_switch_to_attribute(charging_hass_client: MagicMock) -> None:
    charging_hass_client.get_entity_data.return_value = _battery_sensor_data()
    charging_hass_client.get_entity.side_effect = [
        MagicMock(state=State(entity_id="sensor.test_battery_level", state="80", attributes={})),
        MagicMock(state=State(entity_id="sensor.test_battery_level", state="unknown", attributes={})),
    ]
    controller = _get_instance(charging_hass_client)

    assert controller.get_battery_level() == 80
    with pytest.raises(BatteryLevelRetrievalError):
        controller.get_battery_level()

    charging_hass_client.get_entity_data.assert_called_once_with()
    assert [call.kwargs["entity_id"] for call in charging_hass_client.get_entity.call_args_list] == [
        "sensor.test_battery_level",
        "sensor.test_battery_level",
    ]


def test_get_battery_level_falls_back_to_attribute(charging_hass_client: MagicMock) -> None:
    """Without a battery sensor, the battery_level attribute of the main entity is used."""
    charging_hass_client.get_entity.return_value = MagicMock(
        state=State(entity_id="vacuum.test", state="docked", attributes={ATTR_BATTERY_LEVEL: 75}),
    )
    controller = _get_instance(charging_hass_client)
    assert controller.get_battery_level() == 75
    assert controller.battery_level_attribute == ATTR_BATTERY_LEVEL


def test_get_battery_level_no_sensor_no_attribute_error(charging_hass_client: MagicMock) -> None:
    """Error when neither a battery sensor nor the attribute is available."""
    charging_hass_client.get_entity.return_value = MagicMock(
        state=State(entity_id="vacuum.test", state="docked", attributes={}),
    )
    controller = _get_instance(charging_hass_client)
    with pytest.raises(BatteryLevelRetrievalError):
        controller.get_battery_level()


def test_get_battery_level_sensor_invalid_state(charging_hass_client: MagicMock) -> None:
    """Error when the discovered battery sensor state cannot be converted to int."""
    charging_hass_client.get_entity_data.return_value = _battery_sensor_data(battery_state="80")
    charging_hass_client.get_entity.return_value = MagicMock(
        state=State(entity_id="sensor.test_battery_level", state="unknown", attributes={}),
    )
    controller = _get_instance(charging_hass_client)
    with pytest.raises(BatteryLevelRetrievalError):
        controller.get_battery_level()


def test_get_battery_level_reports_disappeared_sensor(charging_hass_client: MagicMock) -> None:
    charging_hass_client.get_entity_data.return_value = _battery_sensor_data()
    charging_hass_client.get_entity.return_value = None

    with pytest.raises(BatteryLevelRetrievalError, match=r"Battery level entity sensor\.test_battery_level not found"):
        _get_instance(charging_hass_client).get_battery_level()

    charging_hass_client.get_entity.assert_called_once_with(entity_id="sensor.test_battery_level")


def test_charging_state_reports_disappeared_vacuum(charging_hass_client: MagicMock) -> None:
    charging_hass_client.get_entity.return_value = None

    with pytest.raises(ControllerError, match=r"Entity vacuum\.test not found"):
        _get_instance(charging_hass_client).is_charging()


def test_is_charging(charging_hass_client: MagicMock) -> None:
    """Test checking if device is charging."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={},
    )

    charging_hass_client.get_entity.return_value = MagicMock(state=mocked_state)
    assert _get_instance(charging_hass_client).is_charging() is True


def test_is_not_charging(charging_hass_client: MagicMock) -> None:
    """Test checking if device is not charging."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="cleaning",
        attributes={},
    )

    charging_hass_client.get_entity.return_value = MagicMock(state=mocked_state)
    assert _get_instance(charging_hass_client).is_charging() is False


def test_is_valid_state(charging_hass_client: MagicMock) -> None:
    """Test checking if device is in a valid state."""
    for state in ["docked", "cleaning", "returning", "idle", "paused"]:
        mocked_state = State(
            entity_id="vacuum.test",
            state=state,
            attributes={},
        )

        charging_hass_client.get_entity.return_value = MagicMock(state=mocked_state)
        assert _get_instance(charging_hass_client).is_valid_state() is True


def test_is_invalid_state(charging_hass_client: MagicMock) -> None:
    """Test checking if device is in an invalid state."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="error",
        attributes={},
    )

    charging_hass_client.get_entity.return_value = MagicMock(state=mocked_state)
    assert _get_instance(charging_hass_client).is_valid_state() is False


def test_connection_validation(charging_hass_client: MagicMock) -> None:
    """Test API connection validation."""
    charging_hass_client.get_config.side_effect = HomeassistantAPIError("Error")
    with pytest.raises(ApiConnectionError):
        HassChargingController(charging_hass_client)


def _get_instance(client: MagicMock) -> HassChargingController:
    return HassChargingController(client, entity_id="vacuum.test")
