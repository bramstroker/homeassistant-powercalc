import pytest
from homeassistant import loader
from pytest_homeassistant_custom_component.common import (
    mock_area_registry,
    mock_device_registry,
    mock_registry,
    MockConfigEntry
)
from homeassistant.const import CONF_ENTITY_ID
from custom_components.powercalc.const import (
    DOMAIN,
    CONF_FIXED,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    SensorType
)

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def enable_custom_integrations(hass):
    """Enable custom integrations defined in the test dir."""
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS)


@pytest.fixture
def area_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_area_registry(hass)


@pytest.fixture
def device_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_device_registry(hass)


@pytest.fixture
def entity_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_registry(hass)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {
                CONF_POWER: 50,
            }
        },
        unique_id="aabbccddeeff",
        title="test"
    )
