from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, cast

from homeassistant.components import websocket_api
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_ICON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import CONF_FIXED_VALUE, CalculationStrategy
from custom_components.powercalc.errors import StrategyConfigurationError, UnsupportedStrategyError
from custom_components.powercalc.flow_helper.common import unwrap_choose_selector
from custom_components.powercalc.power_profile.power_profile import PowerProfile
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from custom_components.powercalc.strategy.selector import detect_calculation_strategy

PREVIEW_NAME = "powercalc"
PREVIEW_FRIENDLY_NAME = "Preview power"
PREVIEW_ICON = "mdi:flash"


class PreviewFlowProtocol(Protocol):
    sensor_config: ConfigType
    selected_profile: PowerProfile | None
    source_entity: SourceEntity | None


async def async_setup_preview(hass: HomeAssistant) -> None:
    """Set up the Powercalc preview websocket command."""
    websocket_api.async_register_command(hass, ws_start_preview)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{PREVIEW_NAME}/start_preview",
        vol.Required("flow_id"): str,
        vol.Required("flow_type"): vol.Any("config_flow", "options_flow"),
        vol.Required("user_input"): dict,
    },
)
@websocket_api.async_response
async def ws_start_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Generate a live Powercalc strategy preview."""
    flow = _get_flow_handler(hass, msg)
    flow_status = _get_flow_status(hass, msg)
    errors = _validate_user_input(flow_status.get("data_schema"), msg["user_input"])
    if errors:
        connection.send_message(
            {
                "id": msg["id"],
                "type": websocket_api.TYPE_RESULT,
                "success": False,
                "error": {"code": "invalid_user_input", "message": errors},
            },
        )
        return

    source_entity = flow.source_entity
    if source_entity is None:
        raise HomeAssistantError("No source entity available for Powercalc preview")

    preview = await build_profile_preview(
        hass,
        _build_preview_sensor_config(flow, flow_status["step_id"], msg["user_input"]),
        source_entity,
        flow.selected_profile,
    )

    connection.send_result(msg["id"])
    connection.send_message(
        websocket_api.event_message(
            msg["id"],
            {
                "attributes": preview["attributes"],
                "state": preview["state"],
            },
        ),
    )
    connection.subscriptions[msg["id"]] = lambda: None


def _get_flow_handler(hass: HomeAssistant, msg: dict[str, Any]) -> PreviewFlowProtocol:
    manager = hass.config_entries.flow if msg["flow_type"] == "config_flow" else hass.config_entries.options
    try:
        return cast(PreviewFlowProtocol, manager._progress[msg["flow_id"]])  # noqa: SLF001
    except KeyError as err:
        raise UnknownFlow from err


def _get_flow_status(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    manager = hass.config_entries.flow if msg["flow_type"] == "config_flow" else hass.config_entries.options
    return cast(dict[str, Any], manager.async_get(msg["flow_id"]))


def _validate_user_input(schema: vol.Schema | None, user_input: dict[str, Any]) -> dict[str, str]:
    if schema is None:
        return {}

    errors: dict[str, str] = {}
    key: vol.Marker
    for key, validator in schema.schema.items():
        if key.schema not in user_input:
            continue
        try:
            validator(user_input[key.schema])
        except vol.Invalid as ex:
            errors[str(key.schema)] = str(ex.msg)
    return errors


def _build_preview_sensor_config(flow: PreviewFlowProtocol, step_id: str, user_input: dict[str, Any]) -> ConfigType:
    sensor_config = dict(flow.sensor_config)
    try:
        strategy = CalculationStrategy(step_id)
    except ValueError:
        return sensor_config

    sensor_config[strategy] = _unwrap_preview_strategy_input(strategy, user_input)
    return sensor_config


def _unwrap_preview_strategy_input(strategy: CalculationStrategy, user_input: dict[str, Any]) -> dict[str, Any]:
    """Unwrap form-only selector wrappers before building a preview strategy config."""
    unwrapped = dict(user_input)
    if strategy == CalculationStrategy.FIXED:
        unwrap_choose_selector(unwrapped, CONF_FIXED_VALUE)
    return unwrapped


async def build_profile_preview(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity,
    power_profile: PowerProfile | None,
) -> dict[str, Any]:
    """Build an entity-like preview containing only current calculated power."""
    current_power = await _calculate_current_power(hass, sensor_config, source_entity, power_profile)
    return {
        "attributes": {
            ATTR_FRIENDLY_NAME: PREVIEW_FRIENDLY_NAME,
            ATTR_ICON: PREVIEW_ICON,
        },
        "state": _format_preview_state(current_power),
    }


async def _calculate_current_power(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity,
    power_profile: PowerProfile | None,
) -> Decimal | None:
    current_state = hass.states.get(source_entity.entity_id)
    if current_state is None:
        return None

    try:
        cv.template_complex(sensor_config)
    except vol.Invalid:
        return None

    strategy = detect_calculation_strategy(sensor_config, power_profile)
    try:
        calculation_strategy = await PowerCalculatorStrategyFactory(hass).create(
            sensor_config,
            strategy,
            power_profile,
            source_entity,
        )
    except (StrategyConfigurationError, UnsupportedStrategyError):
        return None

    try:
        return await calculation_strategy.calculate(current_state)
    except HomeAssistantError:
        return None


def _format_preview_state(power: Decimal | None) -> str:
    if power is None:
        return "unavailable"
    return f"{_format_power(power)} W"


def _format_power(value: Decimal | float | str | None) -> str:
    if value is None:
        return "0"
    decimal_value = Decimal(str(value))
    return f"{decimal_value:.2f}".rstrip("0").rstrip(".")
