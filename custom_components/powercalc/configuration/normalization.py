"""Normalize persisted configuration shapes to runtime mappings."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_ID, CONF_PATH

from custom_components.powercalc.const import CONF_PLAYBOOK_ID, CONF_POWER, CONF_STATE


def normalize_states_power(states_power: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize state-power config to the runtime mapping shape."""
    if isinstance(states_power, list):
        return {item[CONF_STATE]: item[CONF_POWER] for item in states_power}
    return dict(states_power)


def normalize_playbooks(playbooks: dict[str, str] | list[dict[str, str]]) -> dict[str, str]:
    """Normalize playbook config to the runtime id-path mapping shape."""
    if isinstance(playbooks, list):
        return {item[CONF_ID]: item[CONF_PATH] for item in playbooks}
    return dict(playbooks)


def normalize_state_trigger(state_trigger: dict[str, str] | list[dict[str, str]]) -> dict[str, str]:
    """Normalize playbook state-trigger config to the runtime state-playbook mapping shape."""
    if isinstance(state_trigger, list):
        return {item[CONF_STATE]: item[CONF_PLAYBOOK_ID] for item in state_trigger}
    return dict(state_trigger)
