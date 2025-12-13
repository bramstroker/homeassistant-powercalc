import inspect
import logging

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback

from custom_components.powercalc.const import (
    CONF_GROUP,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_TYPE,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    DOMAIN,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    GroupType,
    SensorType,
)

_LOGGER = logging.getLogger(__name__)


async def remove_power_sensor_from_associated_groups(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> list[ConfigEntry]:
    """When the user remove a virtual power config entry we need to update all the groups which this sensor belongs to."""
    group_entries = get_groups_having_member(hass, config_entry)

    for group_entry in group_entries:
        member_sensors = group_entry.data.get(CONF_GROUP_MEMBER_SENSORS) or []
        member_sensors.remove(config_entry.entry_id)

        hass.config_entries.async_update_entry(
            group_entry,
            data={**group_entry.data, CONF_GROUP_MEMBER_SENSORS: member_sensors},
        )

    return group_entries


async def remove_group_from_power_sensor_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> list[ConfigEntry]:
    """When the user removes a group config entry we need to update all the virtual power sensors which reference this group."""
    entries_to_update = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_SENSOR_TYPE) == SensorType.VIRTUAL_POWER and entry.data.get(CONF_GROUP) == config_entry.entry_id
    ]

    for group_entry in entries_to_update:
        hass.config_entries.async_update_entry(
            group_entry,
            data={**group_entry.data, CONF_GROUP: None},
        )

    return entries_to_update


async def add_to_associated_groups(hass: HomeAssistant, config_entry: ConfigEntry) -> ConfigEntry | None:  # type: ignore
    """
    When the user has set a group on a virtual power config entry,
    we need to add this config entry to the group members sensors and update the group.
    """
    sensor_type = config_entry.data.get(CONF_SENSOR_TYPE)
    if sensor_type not in [SensorType.VIRTUAL_POWER, SensorType.DAILY_ENERGY]:
        return None

    if CONF_GROUP not in config_entry.data or not config_entry.data.get(CONF_GROUP):
        return None

    groups: list[str] | str = config_entry.data.get(CONF_GROUP)  # type: ignore
    if not isinstance(groups, list):
        groups = [groups]

    for group_entry_id in groups:
        group_entry = await add_to_associated_group(hass, config_entry, group_entry_id)
        if group_entry:
            _LOGGER.debug(
                "ConfigEntry %s: Added to group %s.",
                config_entry.title,
                group_entry.title,
            )


async def add_to_associated_group(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    group_entry_id: str,
) -> ConfigEntry | None:
    """When the user has set a group on a virtual power config entry,
    we need to add this config entry to the group members sensors and update the group.
    """
    group_entry = hass.config_entries.async_get_entry(group_entry_id)

    # When we are not dealing with a uuid, the user has set a group name manually
    # Create a new group entry for this group
    if not group_entry and len(group_entry_id) != 32:
        group_entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, group_entry_id)
        if not group_entry:
            additional_args: dict = {}
            signature = inspect.signature(ConfigEntry.__init__)
            if "discovery_keys" in signature.parameters:
                additional_args["discovery_keys"] = {}

            if "subentries_data" in signature.parameters:
                additional_args["subentries_data"] = None

            group_entry = ConfigEntry(
                version=ConfigFlow.VERSION,
                minor_version=ConfigFlow.MINOR_VERSION,
                domain=DOMAIN,
                source=SOURCE_IMPORT,
                title=group_entry_id,
                data={
                    CONF_SENSOR_TYPE: SensorType.GROUP,
                    CONF_NAME: group_entry_id,
                },
                options={},
                unique_id=group_entry_id,
                **additional_args,
            )
            await hass.config_entries.async_add(group_entry)

    if not group_entry:
        _LOGGER.warning(
            "ConfigEntry %s: Cannot add/remove to group %s. It does not exist.",
            config_entry.title,
            group_entry_id,
        )
        return None

    member_sensors = set(group_entry.data.get(CONF_GROUP_MEMBER_SENSORS) or [])

    # Config entry has already been added to associated group. just skip adding it again
    if config_entry.entry_id in member_sensors:
        return None

    member_sensors.add(config_entry.entry_id)
    hass.config_entries.async_update_entry(
        group_entry,
        data={**group_entry.data, CONF_GROUP_MEMBER_SENSORS: list(member_sensors)},
    )
    return group_entry


def get_entries_having_subgroup(hass: HomeAssistant, subgroup_entry: ConfigEntry) -> list[ConfigEntry]:
    """Get all virtual power entries which have the subgroup in their subgroups list."""
    return [entry for entry in get_group_entries(hass) if subgroup_entry.entry_id in (entry.data.get(CONF_SUB_GROUPS) or [])]


def get_groups_having_member(hass: HomeAssistant, member_entry: ConfigEntry) -> list[ConfigEntry]:
    """Get all group entries which have the member sensor in their member list."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP and member_entry.entry_id in (entry.data.get(CONF_GROUP_MEMBER_SENSORS) or [])
    ]


@callback
def get_group_entries(hass: HomeAssistant, group_type: GroupType | None = None) -> list[ConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_SENSOR_TYPE) == SensorType.GROUP
        and (group_type is None or entry.data.get(CONF_GROUP_TYPE, GroupType.CUSTOM) == group_type)
    ]


@callback
def get_entries_excluding_global_config(hass: HomeAssistant) -> list[ConfigEntry]:
    return [entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.unique_id != ENTRY_GLOBAL_CONFIG_UNIQUE_ID]
