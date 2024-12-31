import voluptuous as vol
from homeassistant.helpers.selector import selector

from custom_components.powercalc.power_profile.power_profile import PowerProfile


def build_dynamic_field_schema(profile: PowerProfile) -> vol.Schema:
    schema = {}
    for field in profile.custom_fields:
        schema[vol.Required(field.key)] = selector(field.selector)
    return vol.Schema(schema)
