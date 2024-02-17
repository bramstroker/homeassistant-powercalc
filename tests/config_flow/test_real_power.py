from homeassistant import data_entry_flow
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_SENSOR_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS, SensorType
from tests.config_flow.common import (
    create_mock_entry,
    initialize_options_flow,
    select_sensor_type,
)


async def test_real_power(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Washing machine",
            CONF_ENTITY_ID: "sensor.washing_machine_power",
            CONF_CREATE_UTILITY_METERS: True,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()
    assert hass.states.get("sensor.washing_machine_energy")
    assert hass.states.get("sensor.washing_machine_energy_daily")


async def test_energy_sensor_is_bound_to_power_device(hass: HomeAssistant) -> None:
    power_sensor_id = "sensor.my_power"
    device_id = "test"

    entity_registry = mock_registry(
        hass,
        {
            power_sensor_id: RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="123",
                platform="sensor",
                device_id=device_id,
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="foo",
                model="bar",
            ),
        },
    )

    result = await select_sensor_type(hass, SensorType.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: power_sensor_id,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    energy_sensor_entry = entity_registry.async_get("sensor.test_energy")
    assert energy_sensor_entry
    assert energy_sensor_entry.unique_id == "123_energy"
    assert energy_sensor_entry.device_id == device_id


async def test_real_power_options(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "Some name",
            CONF_ENTITY_ID: "sensor.my_real_power",
            CONF_SENSOR_TYPE: SensorType.REAL_POWER,
        },
    )

    result = await initialize_options_flow(hass, entry)

    user_input = {
        CONF_ENTITY_ID: "sensor.my_new_real_power",
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_ENTITY_ID] == "sensor.my_new_real_power"

    state = hass.states.get("sensor.some_name_energy")
    assert state
    assert state.attributes.get("source") == "sensor.my_new_real_power"


async def test_attach_to_custom_device(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/2046"""

    power_sensor_id = "sensor.my_smart_plug"
    device_id = "media_player.my_tv"

    entity_registry = mock_registry(
        hass,
        {
            power_sensor_id: RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="123",
                platform="sensor",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="foo",
                model="bar",
                identifiers={("sensor", "identifier_test")},
                connections={("mac", "30:31:32:33:34:35")},
            ),
        },
    )

    result = await select_sensor_type(hass, SensorType.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.my_smart_plug",
            CONF_DEVICE: device_id,
        },
    )

    await hass.async_block_till_done()

    energy_sensor_entry = entity_registry.async_get("sensor.test_energy")
    assert energy_sensor_entry.device_id == device_id


async def test_no_error_is_raised_when_device_not_exists(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.REAL_POWER)
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.my_smart_plug",
            CONF_DEVICE: "non_existing",
        },
    )

    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy")
