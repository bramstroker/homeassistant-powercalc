import pytest
import voluptuous as vol

from custom_components.powercalc.common import validate_is_number, validate_name_pattern


async def test_valid_name_pattern() -> None:
    assert validate_name_pattern("{} energy") == "{} energy"


async def test_invalid_name_pattern() -> None:
    with pytest.raises(vol.Invalid):
        validate_name_pattern("energy")


@pytest.mark.parametrize(
    "number",
    ["20", "10.60", "0", "100000"],
)
async def test_validate_is_number_valid(number: str) -> None:
    assert validate_is_number(number) == number


@pytest.mark.parametrize(
    "number",
    ["test", "45test", "50,1"],
)
async def test_validate_is_number_invalid(number: str) -> None:
    with pytest.raises(vol.Invalid):
        validate_is_number(number)
