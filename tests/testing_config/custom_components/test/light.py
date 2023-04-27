"""
Provide a mock light platform.

Call init before using it in your tests to ensure clean test data.
"""
import uuid

from homeassistant.components.light import LightEntity
from homeassistant.const import STATE_OFF, STATE_ON
from pytest_homeassistant_custom_component.common import MockToggleEntity

ENTITIES = []


def init(empty=False):
    """Initialize the platform with entities."""
    global ENTITIES

    ENTITIES = (
        []
        if empty
        else [
            MockLight("Ceiling", STATE_ON),
            MockLight("Ceiling", STATE_OFF),
            MockLight(None, STATE_OFF),
        ]
    )


async def async_setup_platform(
    hass, config, async_add_entities_callback, discovery_info=None
):
    """Return mock entities."""
    async_add_entities_callback(ENTITIES)


async def async_setup_entry(hass, entry, async_add_entities) -> bool:
    async_add_entities(ENTITIES)
    return True


class MockLight(MockToggleEntity, LightEntity):
    """Mock light class."""

    color_mode = None
    max_mireds = 500
    min_mireds = 153
    supported_color_modes = None
    supported_features = 0

    brightness = None
    color_temp = None
    hs_color = None
    rgb_color = None
    rgbw_color = None
    rgbww_color = None
    xy_color = None
    white_value = None
    manufacturer: str | None = None
    model: str | None = None

    def __init__(
        self, name: str, state: str | None = None, unique_id: str | None = None
    ):
        if state is None:
            state = STATE_ON
        super().__init__(name, state)
        if unique_id is None:
            unique_id = str(uuid.uuid4())[:8]
        self._attr_unique_id = unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {("hue", self.unique_id)},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
        }

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        super().turn_on(**kwargs)
        for key, value in kwargs.items():
            if key in [
                "brightness",
                "hs_color",
                "xy_color",
                "rgb_color",
                "rgbw_color",
                "rgbww_color",
                "color_temp",
                "white_value",
            ]:
                setattr(self, key, value)
            if key == "white":
                setattr(self, "brightness", value)
