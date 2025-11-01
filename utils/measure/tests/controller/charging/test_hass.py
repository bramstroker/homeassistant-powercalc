from unittest.mock import MagicMock, patch

from homeassistant_api import Client, State
from homeassistant_api.errors import HomeassistantAPIError
from measure.const import QUESTION_ENTITY_ID
from measure.controller.charging.const import (
    QUESTION_BATTERY_LEVEL_ATTRIBUTE,
    QUESTION_BATTERY_LEVEL_ENTITY,
    QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
    BatteryLevelSourceType,
    ChargingDeviceType,
)
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.charging.hass import ATTR_BATTERY_LEVEL, HassChargingController
from measure.controller.errors import ApiConnectionError
from measure.runner.const import QUESTION_CHARGING_DEVICE_TYPE
import pytest


def test_get_battery_level_attribute() -> None:
    """Test retrieving battery level from an attribute."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={ATTR_BATTERY_LEVEL: 75},
    )

    with patch.multiple(
        "homeassistant_api.Client",
        get_entity=MagicMock(return_value=MagicMock(state=mocked_state)),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
                QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ATTRIBUTE,
                QUESTION_BATTERY_LEVEL_ATTRIBUTE: ATTR_BATTERY_LEVEL,
            },
        )

        assert hass_controller.get_battery_level() == 75


def test_get_battery_level_entity() -> None:
    """Test retrieving battery level from a separate entity."""
    mocked_entity = MagicMock()
    mocked_entity.state = State(
        entity_id="sensor.vacuum_battery",
        state="80",
        attributes={},
    )

    with patch.multiple(
        "homeassistant_api.Client",
        get_entity=MagicMock(return_value=mocked_entity),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
                QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ENTITY,
                QUESTION_BATTERY_LEVEL_ENTITY: "sensor.vacuum_battery",
            },
        )

        assert hass_controller.get_battery_level() == 80


def test_get_battery_level_attribute_error() -> None:
    """Test error when attribute is missing."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={},
    )

    with (
        patch.multiple(
            "homeassistant_api.Client",
            get_entity=MagicMock(return_value=MagicMock(state=mocked_state)),
            get_config=MagicMock(return_value={}),
        ),
        pytest.raises(BatteryLevelRetrievalError),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
                QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ATTRIBUTE,
                QUESTION_BATTERY_LEVEL_ATTRIBUTE: ATTR_BATTERY_LEVEL,
            },
        )

        hass_controller.get_battery_level()


def test_get_battery_level_entity_error() -> None:
    """Test error when entity is not found."""
    with (
        patch.multiple(
            "homeassistant_api.Client",
            get_entity=MagicMock(return_value=None),
            get_config=MagicMock(return_value={}),
        ),
        pytest.raises(BatteryLevelRetrievalError),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
                QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ENTITY,
                QUESTION_BATTERY_LEVEL_ENTITY: "sensor.vacuum_battery",
            },
        )

        hass_controller.get_battery_level()


def test_get_battery_level_entity_invalid_state() -> None:
    """Test error when entity state cannot be converted to int."""
    mocked_entity = MagicMock()
    mocked_entity.state = State(
        entity_id="sensor.vacuum_battery",
        state="unknown",
        attributes={},
    )

    with (
        patch.multiple(
            "homeassistant_api.Client",
            get_entity=MagicMock(return_value=mocked_entity),
            get_config=MagicMock(return_value={}),
        ),
        pytest.raises(BatteryLevelRetrievalError),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
                QUESTION_BATTERY_LEVEL_SOURCE_TYPE: BatteryLevelSourceType.ENTITY,
                QUESTION_BATTERY_LEVEL_ENTITY: "sensor.vacuum_battery",
            },
        )

        hass_controller.get_battery_level()


def test_is_charging() -> None:
    """Test checking if device is charging."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="docked",
        attributes={},
    )

    with patch.multiple(
        "homeassistant_api.Client",
        get_entity=MagicMock(return_value=MagicMock(state=mocked_state)),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
            },
        )

        assert hass_controller.is_charging() is True


def test_is_not_charging() -> None:
    """Test checking if device is not charging."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="cleaning",
        attributes={},
    )

    with patch.multiple(
        "homeassistant_api.Client",
        get_entity=MagicMock(return_value=MagicMock(state=mocked_state)),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
            },
        )

        assert hass_controller.is_charging() is False


def test_is_valid_state() -> None:
    """Test checking if device is in a valid state."""
    for state in ["docked", "cleaning", "returning", "idle", "paused"]:
        mocked_state = State(
            entity_id="vacuum.test",
            state=state,
            attributes={},
        )

        with patch.multiple(
            "homeassistant_api.Client",
            get_entity=MagicMock(return_value=MagicMock(state=mocked_state)),
            get_config=MagicMock(return_value={}),
        ):
            hass_controller = _get_instance()
            hass_controller.process_answers(
                {
                    QUESTION_ENTITY_ID: "vacuum.test",
                    QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
                },
            )

            assert hass_controller.is_valid_state() is True


def test_is_invalid_state() -> None:
    """Test checking if device is in an invalid state."""
    mocked_state = State(
        entity_id="vacuum.test",
        state="error",
        attributes={},
    )

    with patch.multiple(
        "homeassistant_api.Client",
        get_entity=MagicMock(return_value=MagicMock(state=mocked_state)),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = _get_instance()
        hass_controller.process_answers(
            {
                QUESTION_ENTITY_ID: "vacuum.test",
                QUESTION_CHARGING_DEVICE_TYPE: ChargingDeviceType.VACUUM_ROBOT,
            },
        )

        assert hass_controller.is_valid_state() is False


def test_connection_validation() -> None:
    """Test API connection validation."""
    with (
        patch.object(
            Client,
            "get_config",
            side_effect=HomeassistantAPIError("Error"),
        ),
        pytest.raises(ApiConnectionError),
    ):
        HassChargingController("http://localhost:812", "abc")


def test_get_questions() -> None:
    """Test question generation."""
    hass_controller = _get_instance()
    with patch.object(
        Client,
        "get_entities",
        return_value={
            "vacuum": MagicMock(
                entities={
                    "vacuum.test1": MagicMock(entity_id="vacuum.test1"),
                    "vacuum.test2": MagicMock(entity_id="vacuum.test2"),
                },
            ),
        },
    ):
        hass_controller.charging_device_type = ChargingDeviceType.VACUUM_ROBOT
        questions = hass_controller.get_questions()

        # Should have at least entity ID and battery level source type questions
        assert len(questions) >= 2
        assert questions[0].name == QUESTION_ENTITY_ID
        assert questions[1].name == QUESTION_BATTERY_LEVEL_SOURCE_TYPE


def _get_instance() -> HassChargingController:
    """Get a mocked instance of HassChargingController."""
    with patch.multiple(
        "homeassistant_api.Client",
        get_config=MagicMock(return_value={}),
    ):
        return HassChargingController("http://localhost:812", "abc")
