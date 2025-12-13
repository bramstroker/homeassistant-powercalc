from collections import defaultdict

from homeassistant.const import CONF_SENSOR_TYPE
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import DATA_ANALYTICS, DATA_POWER_PROFILES, DOMAIN, SensorType
from custom_components.powercalc.power_profile.power_profile import PowerProfile
from custom_components.powercalc.sensors.group.config_entry_utils import get_entries_excluding_global_config


async def get_count_by_sensor_type(hass: HomeAssistant) -> dict[SensorType, int]:
    count_per_type = {}
    entries = get_entries_excluding_global_config(hass)
    for e in entries:
        sensor_type = SensorType(e.data.get(CONF_SENSOR_TYPE, SensorType.VIRTUAL_POWER))
        if sensor_type not in count_per_type:
            count_per_type[sensor_type] = 0
        count_per_type[sensor_type] += 1
    return count_per_type


def get_manufacturer_counts(hass: HomeAssistant) -> dict[str, int]:
    profiles: list[PowerProfile] = hass.data[DOMAIN][DATA_ANALYTICS].setdefault(DATA_POWER_PROFILES, [])
    counts: dict[str, int] = defaultdict(int)

    for profile in profiles:
        counts[profile.manufacturer] += 1

    return dict(counts)


def get_model_counts(hass: HomeAssistant) -> dict[str, int]:
    profiles: list[PowerProfile] = hass.data[DOMAIN][DATA_ANALYTICS].setdefault(DATA_POWER_PROFILES, [])
    counts: dict[str, int] = defaultdict(int)

    for profile in profiles:
        key = f"{profile.manufacturer}:{profile.model}"
        counts[key] += 1

    return dict(counts)
