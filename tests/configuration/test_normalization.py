from typing import Any

from homeassistant.const import CONF_ID, CONF_PATH
import pytest

from custom_components.powercalc.configuration.normalization import (
    normalize_playbooks,
    normalize_state_trigger,
    normalize_states_power,
)
from custom_components.powercalc.const import CONF_PLAYBOOK_ID, CONF_POWER, CONF_STATE


@pytest.mark.parametrize(
    "states_power, expected",
    [
        (
            [{CONF_STATE: "playing", CONF_POWER: 10}, {CONF_STATE: "paused", CONF_POWER: 5}],
            {"playing": 10, "paused": 5},
        ),
        ({"playing": 10, "paused": 5}, {"playing": 10, "paused": 5}),
        ([], {}),
        ({}, {}),
    ],
)
async def test_normalize_states_power(
    states_power: dict[str, Any] | list[dict[str, Any]],
    expected: dict[str, Any],
) -> None:
    assert normalize_states_power(states_power) == expected


@pytest.mark.parametrize(
    "playbooks, expected",
    [
        ([{CONF_ID: "program1", CONF_PATH: "program1.csv"}], {"program1": "program1.csv"}),
        ({"program1": "program1.csv"}, {"program1": "program1.csv"}),
        ([], {}),
        ({}, {}),
    ],
)
async def test_normalize_playbooks(playbooks: dict[str, str] | list[dict[str, str]], expected: dict[str, str]) -> None:
    assert normalize_playbooks(playbooks) == expected


@pytest.mark.parametrize(
    "state_trigger, expected",
    [
        ([{CONF_STATE: "playing", CONF_PLAYBOOK_ID: "program1"}], {"playing": "program1"}),
        ({"playing": "program1"}, {"playing": "program1"}),
        ([], {}),
        ({}, {}),
    ],
)
async def test_normalize_state_trigger(
    state_trigger: dict[str, str] | list[dict[str, str]],
    expected: dict[str, str],
) -> None:
    assert normalize_state_trigger(state_trigger) == expected


async def test_normalization_returns_a_copy() -> None:
    """Normalizing a mapping must not hand back the caller's dict."""
    states_power = {"playing": 10}
    playbooks = {"program1": "program1.csv"}
    state_trigger = {"playing": "program1"}

    assert normalize_states_power(states_power) is not states_power
    assert normalize_playbooks(playbooks) is not playbooks
    assert normalize_state_trigger(state_trigger) is not state_trigger
