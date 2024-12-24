from unittest.mock import MagicMock, patch

from homeassistant_api import State
from measure.controller.light.hass import HassLightController


def test_get_light_info() -> None:
    mocked_state = State(
        entity_id="light.test",
        state="on",
        attributes={"min_color_temp_kelvin": 2202, "max_color_temp_kelvin": 6535},
    )
    with patch.multiple(
        "homeassistant_api.Client",
        get_state=MagicMock(return_value=mocked_state),
        get_config=MagicMock(return_value={}),
    ):
        hass_controller = HassLightController("http://localhost:812", "abc", 0)
        light_info = hass_controller.get_light_info()
        assert light_info.get_min_mired() == 153
        assert light_info.get_max_mired() == 454
