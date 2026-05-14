import json
from pathlib import Path

from custom_components.powercalc.const import CONF_DAILY_ENERGY_VALUE, CONF_FIXED_VALUE


def test_choose_selector_translations_use_choices_key() -> None:
    translations = json.loads(Path("custom_components/powercalc/translations/en.json").read_text())

    fixed_translations = translations["selector"][CONF_FIXED_VALUE]
    assert fixed_translations["choices"] == {
        "power": "Power",
        "power_template": "Power template",
        "states_power": "States power",
    }
    assert "options" not in fixed_translations

    daily_energy_translations = translations["selector"][CONF_DAILY_ENERGY_VALUE]
    assert daily_energy_translations["choices"] == {
        "value": "Value",
        "value_template": "Value template",
    }
    assert "options" not in daily_energy_translations
