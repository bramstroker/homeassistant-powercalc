import pytest
import voluptuous as vol

from custom_components.powercalc.common import validate_name_pattern


async def test_valid_name_pattern():
    assert validate_name_pattern("{} energy") == "{} energy"


async def test_invalid_name_pattern():
    with pytest.raises(vol.Invalid):
        validate_name_pattern("energy")
