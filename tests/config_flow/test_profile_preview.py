from __future__ import annotations

# ruff: noqa: SLF001
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components import websocket_api
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_ICON, CONF_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.exceptions import HomeAssistantError
import pytest
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.flow_helper import profile_preview
from custom_components.powercalc.flow_helper.profile_preview import (
    PREVIEW_FRIENDLY_NAME,
    PREVIEW_ICON,
    async_setup_preview,
    build_profile_preview,
    ws_start_preview,
)
from tests.config_flow.common import (
    create_mock_entry,
    fixed_value_choice,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
)

SOURCE_ENTITY = SourceEntity("test", "light.test", "light")


def _build_ws_message(flow_id: str, user_input: dict[str, Any], flow_type: str = "config_flow", msg_id: int = 1) -> dict[str, Any]:
    return {
        "id": msg_id,
        "type": "powercalc/start_preview",
        "flow_id": flow_id,
        "flow_type": flow_type,
        "user_input": user_input,
    }


def _make_ws_connection() -> MagicMock:
    connection = MagicMock()
    connection.subscriptions = {}
    return connection


async def test_async_setup_preview_registers_websocket_command(hass: HomeAssistant) -> None:
    with patch.object(websocket_api, "async_register_command") as register_command:
        await async_setup_preview(hass)

    register_command.assert_called_once_with(hass, ws_start_preview)


async def test_build_profile_preview_returns_current_power(hass: HomeAssistant) -> None:
    hass.states.async_set(SOURCE_ENTITY.entity_id, STATE_ON)

    preview = await build_profile_preview(
        hass,
        {CalculationStrategy.FIXED: {CONF_POWER: 12.345}},
        SOURCE_ENTITY,
        None,
    )

    assert preview == {
        "attributes": {
            ATTR_FRIENDLY_NAME: PREVIEW_FRIENDLY_NAME,
            ATTR_ICON: PREVIEW_ICON,
        },
        "state": "12.35 W",
    }


async def test_build_profile_preview_returns_unavailable_without_current_state(hass: HomeAssistant) -> None:
    preview = await build_profile_preview(
        hass,
        {CalculationStrategy.FIXED: {CONF_POWER: 12}},
        SOURCE_ENTITY,
        None,
    )

    assert preview["state"] == STATE_UNAVAILABLE


async def test_build_profile_preview_returns_unavailable_when_strategy_cannot_be_created(hass: HomeAssistant) -> None:
    hass.states.async_set(SOURCE_ENTITY.entity_id, STATE_ON)

    with patch(
        "custom_components.powercalc.flow_helper.profile_preview.PowerCalculatorStrategyFactory.create",
        side_effect=StrategyConfigurationError("invalid"),
    ):
        preview = await build_profile_preview(
            hass,
            {CalculationStrategy.FIXED: {CONF_POWER: 12}},
            SOURCE_ENTITY,
            None,
        )

    assert preview["state"] == STATE_UNAVAILABLE


async def test_build_profile_preview_returns_unavailable_for_invalid_template(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mid-typing templates (e.g. '{{') should silently render as unavailable.

    Mirrors HA core's behavior of suppressing template render errors during preview
    so the log doesn't get flooded with TemplateSyntaxError per keystroke.
    """
    hass.states.async_set(SOURCE_ENTITY.entity_id, STATE_ON)

    preview = await build_profile_preview(
        hass,
        {CalculationStrategy.FIXED: {CONF_POWER_TEMPLATE: "{{"}},
        SOURCE_ENTITY,
        None,
    )

    assert preview["state"] == STATE_UNAVAILABLE
    assert "Could not render power template" not in caplog.text


async def test_build_profile_preview_returns_unavailable_when_calculation_fails(hass: HomeAssistant) -> None:
    hass.states.async_set(SOURCE_ENTITY.entity_id, STATE_ON)
    calculation_strategy = MagicMock()
    calculation_strategy.calculate = AsyncMock(side_effect=HomeAssistantError("failed"))

    with patch(
        "custom_components.powercalc.flow_helper.profile_preview.PowerCalculatorStrategyFactory.create",
        return_value=calculation_strategy,
    ):
        preview = await build_profile_preview(
            hass,
            {CalculationStrategy.FIXED: {CONF_POWER: 12}},
            SOURCE_ENTITY,
            None,
        )

    assert preview["state"] == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "use_schema,user_input,expected",
    [
        (False, {CONF_POWER: "not-a-number"}, {}),
        (True, {"missing": "field"}, {}),
        (True, {CONF_POWER: "10"}, {}),
        (True, {CONF_POWER: "not-a-number"}, {CONF_POWER: "expected float"}),
    ],
)
def test_validate_user_input(use_schema: bool, user_input: dict, expected: dict) -> None:
    schema = vol.Schema(
        {
            vol.Required(CONF_POWER): vol.Coerce(float),
            vol.Optional("ignored"): str,
        },
    )

    assert profile_preview._validate_user_input(schema if use_schema else None, user_input) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "0"),
        (0, "0"),
        (12, "12"),
        (12.5, "12.5"),
        (Decimal("12.345"), "12.34"),
        ("7.5", "7.5"),
    ],
)
def test_format_power(value: None | float | Decimal, expected: str) -> None:
    assert profile_preview._format_power(value) == expected


def test_build_preview_sensor_config_merges_strategy_options() -> None:
    flow = MagicMock()
    flow.sensor_config = {CONF_ENTITY_ID: "light.test"}

    config = profile_preview._build_preview_sensor_config(flow, Step.FIXED, fixed_value_choice(CONF_POWER, 20))

    assert config == {CONF_ENTITY_ID: "light.test", CalculationStrategy.FIXED: {CONF_POWER: 20}}


def test_build_preview_sensor_config_ignores_non_strategy_step() -> None:
    flow = MagicMock()
    flow.sensor_config = {CONF_ENTITY_ID: "light.test"}

    config = profile_preview._build_preview_sensor_config(flow, Step.VIRTUAL_POWER, {CONF_POWER: 20})

    assert config == {CONF_ENTITY_ID: "light.test"}


async def test_preview_websocket_returns_state_for_config_flow(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    assert result["preview"] == "powercalc"
    hass.states.async_set("light.test", STATE_ON)

    connection = _make_ws_connection()
    ws_start_preview(hass, connection, _build_ws_message(result["flow_id"], fixed_value_choice(CONF_POWER, 42)))
    await hass.async_block_till_done()

    connection.send_result.assert_called_once_with(1)
    event = connection.send_message.call_args.args[0]
    assert event["type"] == "event"
    assert event["event"] == {
        "attributes": {ATTR_FRIENDLY_NAME: PREVIEW_FRIENDLY_NAME, ATTR_ICON: PREVIEW_ICON},
        "state": "42 W",
    }
    assert 1 in connection.subscriptions


async def test_preview_websocket_sends_invalid_user_input_error(hass: HomeAssistant) -> None:
    """Cover the schema-validation error response branch.

    `manager.async_get` doesn't expose data_schema, so we patch _get_flow_status
    to inject one and verify the error response is sent.
    """
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    schema = vol.Schema({vol.Optional(CONF_POWER): vol.Coerce(float)})

    connection = _make_ws_connection()
    with patch.object(
        profile_preview,
        "_get_flow_status",
        return_value={"step_id": Step.FIXED, "data_schema": schema},
    ):
        ws_start_preview(hass, connection, _build_ws_message(result["flow_id"], {CONF_POWER: "not-a-number"}))
        await hass.async_block_till_done()

    connection.send_result.assert_not_called()
    error_message = connection.send_message.call_args.args[0]
    assert error_message["type"] == websocket_api.TYPE_RESULT
    assert error_message["success"] is False
    assert error_message["error"]["code"] == "invalid_user_input"
    assert error_message["error"]["message"] == {CONF_POWER: "expected float"}


async def test_preview_websocket_for_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 10},
        },
    )
    result = await initialize_options_flow(hass, entry, Step.FIXED)
    hass.states.async_set("light.test", STATE_ON)

    connection = _make_ws_connection()
    ws_start_preview(
        hass,
        connection,
        _build_ws_message(result["flow_id"], fixed_value_choice(CONF_POWER, 25), flow_type="options_flow"),
    )
    await hass.async_block_till_done()

    connection.send_result.assert_called_once_with(1)
    event = connection.send_message.call_args.args[0]
    assert event["event"]["state"] == "25 W"


async def test_preview_websocket_raises_for_unknown_flow(hass: HomeAssistant) -> None:
    connection = _make_ws_connection()
    ws_start_preview(hass, connection, _build_ws_message("does-not-exist", {CONF_POWER: 10}))
    await hass.async_block_till_done()

    connection.async_handle_exception.assert_called_once()
    assert isinstance(connection.async_handle_exception.call_args.args[1], UnknownFlow)


async def test_preview_websocket_raises_when_source_entity_missing(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    flow.source_entity = None

    connection = _make_ws_connection()
    ws_start_preview(hass, connection, _build_ws_message(result["flow_id"], {CONF_POWER: 10}))
    await hass.async_block_till_done()

    connection.async_handle_exception.assert_called_once()
    err = connection.async_handle_exception.call_args.args[1]
    assert isinstance(err, HomeAssistantError)
    assert "No source entity" in str(err)
