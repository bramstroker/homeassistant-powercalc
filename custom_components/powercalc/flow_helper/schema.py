from homeassistant.components.utility_meter import CONF_METER_TYPE, METER_TYPES
from homeassistant.const import UnitOfPower
from homeassistant.helpers import selector
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode
import voluptuous as vol

from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_FILTER_OUTLIER_ENABLED,
    CONF_ENERGY_FILTER_OUTLIER_MAX,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_SUB_PROFILE,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    ENERGY_INTEGRATION_METHOD_LEFT,
    ENERGY_INTEGRATION_METHODS,
    UnitPrefix,
)
from custom_components.powercalc.power_profile.power_profile import PowerProfile

SCHEMA_UTILITY_METER_TOGGLE = vol.Schema(
    {
        vol.Optional(CONF_CREATE_UTILITY_METERS, default=False): selector.BooleanSelector(),
    },
)

SCHEMA_ENERGY_SENSOR_TOGGLE = vol.Schema(
    {
        vol.Optional(CONF_CREATE_ENERGY_SENSOR, default=True): selector.BooleanSelector(),
    },
)

SCHEMA_ENERGY_OPTIONS = vol.Schema(
    {
        vol.Optional(
            CONF_ENERGY_INTEGRATION_METHOD,
            default=ENERGY_INTEGRATION_METHOD_LEFT,
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=ENERGY_INTEGRATION_METHODS,
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
        vol.Optional(CONF_ENERGY_SENSOR_UNIT_PREFIX): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=UnitPrefix.KILO, label="k (kilo)"),
                    selector.SelectOptionDict(value=UnitPrefix.MEGA, label="M (mega)"),
                    selector.SelectOptionDict(value=UnitPrefix.GIGA, label="G (giga)"),
                    selector.SelectOptionDict(value=UnitPrefix.TERA, label="T (tera)"),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
    },
)

SCHEMA_SENSOR_ENERGY_OPTIONS = SCHEMA_ENERGY_OPTIONS.extend(
    vol.Schema(
        {
            vol.Optional(CONF_ENERGY_FILTER_OUTLIER_ENABLED, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_ENERGY_FILTER_OUTLIER_MAX): NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, unit_of_measurement=UnitOfPower.WATT),
            ),
        },
    ).schema,
)


SCHEMA_UTILITY_METER_OPTIONS = vol.Schema(
    {
        vol.Required(CONF_UTILITY_METER_TYPES): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=METER_TYPES,
                translation_key=CONF_METER_TYPE,
                multiple=True,
            ),
        ),
        vol.Optional(CONF_UTILITY_METER_TARIFFS, default=[]): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[], custom_value=True, multiple=True),
        ),
        vol.Optional(CONF_UTILITY_METER_NET_CONSUMPTION, default=False): selector.BooleanSelector(),
        vol.Required(CONF_UTILITY_METER_OFFSET, default=0): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=28,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="days",
            ),
        ),
    },
)


async def build_sub_profile_schema(
    profile: PowerProfile,
    selected_sub_profile: str | None,
) -> vol.Schema:
    """Create sub profile schema."""
    sub_profiles = [
        selector.SelectOptionDict(
            value=sub_profile[0],
            label=sub_profile[1]["name"] if "name" in sub_profile[1] else sub_profile[0],
        )
        for sub_profile in await profile.get_sub_profiles()
    ]
    return vol.Schema(
        {
            vol.Required(
                CONF_SUB_PROFILE,
                description={"suggested_value": selected_sub_profile},
                default=selected_sub_profile,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sub_profiles,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
        },
    )
