from decimal import Decimal

import pytest
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.helpers import evaluate_power, get_or_create_unique_id


@pytest.mark.parametrize(
    "power,output",
    [
        (Template("unknown"), None),
        (Template("{{ 1 + 3 | float }}"), Decimal(4.0)),
        (20.5, Decimal(20.5)),
        ("foo", None),
        (Decimal(40.65), Decimal(40.65)),
        ((1, 2), None),
    ],
)
async def test_evaluate_power(
    hass: HomeAssistant,
    power: Template | Decimal | float,
    output: Decimal | None,
) -> None:
    if isinstance(power, Template):
        power.hass = hass
    assert await evaluate_power(power) == output


async def test_get_unique_id_from_config() -> None:
    config = {CONF_UNIQUE_ID: "1234"}
    assert get_or_create_unique_id(config, SourceEntity("test", "light.test", "light"), None) == "1234"


async def test_get_unique_id_generated() -> None:
    unique_id = get_or_create_unique_id({}, SourceEntity("test", "light.test", "light"), None)
    assert len(unique_id) == 13
