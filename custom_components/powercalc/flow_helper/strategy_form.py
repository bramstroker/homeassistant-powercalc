from __future__ import annotations

from typing import Any

from custom_components.powercalc.const import (
    CONF_FIXED_VALUE,
    CONF_PLAYBOOK_ID,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_STATE,
    CONF_STATE_TRIGGER,
    CONF_STATES_POWER,
    CalculationStrategy,
)
from custom_components.powercalc.flow_helper.common import unwrap_choose_selector, wrap_choose_selector

FIXED_CHOICES: dict[str, list[str] | str] = {
    CONF_STATES_POWER: CONF_STATES_POWER,
    CONF_POWER_TEMPLATE: CONF_POWER_TEMPLATE,
    CONF_POWER: CONF_POWER,
}


def order_choices_for_default[T](
    choices: dict[str, T],
    default_choice: str | None,
) -> dict[str, T]:
    """Put the default choice first because HA initializes choose selectors from the first choice."""
    if default_choice not in choices:
        return choices
    return {
        default_choice: choices[default_choice],
        **{choice: config for choice, config in choices.items() if choice != default_choice},
    }


def has_saved_choice_value(value: object) -> bool:
    """Return whether a saved strategy value should drive the selected form choice."""
    if value is None:
        return False
    if isinstance(value, (str, list, dict)):
        return bool(value)
    return True


def find_present_choice(form_data: dict[str, Any], choices: dict[str, list[str] | str]) -> str | None:
    """Find the first choice that has matching config data."""
    for choice_id, mapping in choices.items():
        keys = [mapping] if isinstance(mapping, str) else mapping
        if any(has_saved_choice_value(form_data.get(key)) for key in keys):
            return choice_id
    return None


def fixed_choice_key_from_validated_value(value: object) -> str:
    """Infer the fixed strategy config key from a validated ChooseSelector value."""
    if isinstance(value, list):
        return CONF_STATES_POWER
    if isinstance(value, str):
        return CONF_POWER_TEMPLATE
    return CONF_POWER


def unwrap_strategy_user_input(strategy: CalculationStrategy, user_input: dict[str, Any]) -> dict[str, Any]:
    """Unwrap form-only selector wrappers and normalize strategy user input."""
    if strategy == CalculationStrategy.FIXED:
        unwrap_choose_selector(user_input, CONF_FIXED_VALUE, fixed_choice_key_from_validated_value)
    if CONF_STATE_TRIGGER in user_input and isinstance(user_input[CONF_STATE_TRIGGER], list):
        user_input[CONF_STATE_TRIGGER] = {
            item[CONF_STATE]: item[CONF_PLAYBOOK_ID] for item in user_input[CONF_STATE_TRIGGER]
        }
    return user_input


def wrap_strategy_form_data(strategy: CalculationStrategy, form_data: dict[str, Any]) -> dict[str, Any]:
    """Wrap stored strategy config back into form-only selector structures."""
    if strategy == CalculationStrategy.FIXED:
        choices = order_choices_for_default(FIXED_CHOICES, find_present_choice(form_data, FIXED_CHOICES))
        form_data = wrap_choose_selector(form_data, CONF_FIXED_VALUE, choices, raw_value=True)
    if CONF_STATE_TRIGGER in form_data and isinstance(form_data[CONF_STATE_TRIGGER], dict):
        form_data = {
            **form_data,
            CONF_STATE_TRIGGER: [
                {CONF_STATE: state, CONF_PLAYBOOK_ID: playbook_id}
                for state, playbook_id in form_data[CONF_STATE_TRIGGER].items()
            ],
        }
    return form_data
