from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.loader.local import LocalLoader


async def test_load_model_returns_none_when_not_found(hass: HomeAssistant) -> None:
    loader = LocalLoader(hass)
    assert not await loader.load_model("foo", "bar", None)
