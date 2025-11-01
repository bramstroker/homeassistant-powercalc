from homeassistant.helpers.selector import selector
import voluptuous as vol

from custom_components.powercalc.power_profile.power_profile import PowerProfile


def build_dynamic_field_schema(profile: PowerProfile) -> vol.Schema:
    schema = {}
    for field in profile.custom_fields:
        field_description = field.description
        if not field_description:
            field_description = field.label
        key = vol.Required(field.key, description=field_description)
        schema[key] = selector(field.selector)
    return vol.Schema(schema)
