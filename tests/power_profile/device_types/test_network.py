from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL, DUMMY_ENTITY_ID
from tests.common import run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_network_device(hass: HomeAssistant) -> None:
    """
    Test that wifi repeater can be setup from profile library
    """
    binary_sensor_id = "binary_sensor.wifi_repeater"
    manufacturer = "AVM"
    model = "FRITZ!Repeater 1200 AX"

    power_sensor_id = "sensor.wifi_repeater_device_power"

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: binary_sensor_id,
            CONF_MANUFACTURER: manufacturer,
            CONF_MODEL: model,
        },
    )

    power_state = hass.states.get(power_sensor_id)
    assert power_state
    assert power_state.state == "unavailable"

    hass.states.async_set(binary_sensor_id, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "3.00"

    hass.states.async_set(binary_sensor_id, STATE_OFF)
    await hass.async_block_till_done()

    assert hass.states.get(power_sensor_id).state == "0.00"


async def test_router_discovery_by_device(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
    mock_flow_init: AsyncMock,
) -> None:
    """
    Test that smart plug can be setup from profile library
    """

    mock_entity_with_model_information(
        "switch.freebox",
        "test",
        "network_router",
    )

    await run_powercalc_setup(hass)

    mock_calls = mock_flow_init.mock_calls
    assert len(mock_calls) == 1
    assert mock_calls[0][2]["context"] == {"source": SOURCE_INTEGRATION_DISCOVERY}
    discovery_data = mock_calls[0][2]["data"]
    assert discovery_data["entity_id"] == DUMMY_ENTITY_ID
