from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.loader.composite import CompositeLoader
from custom_components.powercalc.power_profile.loader.local import LocalLoader


async def test_composite_can_return_none(hass: HomeAssistant) -> None:
    sub_loader = LocalLoader(hass, "")
    sub_loader.load_model = AsyncMock(return_value=None)
    loader = CompositeLoader([sub_loader])
    assert not await loader.load_model("foo", "bar")
