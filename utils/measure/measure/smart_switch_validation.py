"""Shared relay/device checks for the smart-switch measurement entry points.

The CLI and the Home Assistant app validate the same selection. Both must treat the
channels of one physical device (a power strip) as one device, otherwise sibling
relays are rejected or a sibling's built-in power sensor passes as an external meter.
"""

from collections.abc import Sequence
from typing import Protocol


class GroupedEntity(Protocol):
    """The registry fields the smart-switch checks need."""

    device_id: str | None
    device_group_id: str | None


SAME_DEVICE_ERROR = "All selected relays must belong to the same Home Assistant device"
SELF_METER_ERROR = "Measure switch self consumption with an external power meter, not its own sensor"


def relay_device_ids(relays: Sequence[GroupedEntity]) -> set[str | None]:
    """Return one physical device ID per relay, grouping the channels of a product."""

    return {relay.device_group_id or relay.device_id for relay in relays}


def smart_switch_selection_error(
    relays: Sequence[GroupedEntity],
    meter: GroupedEntity | None = None,
) -> str | None:
    """Return the first selection error, or ``None`` when the selection is valid."""

    device_ids = relay_device_ids(relays)
    if None in device_ids or len(device_ids) != 1:
        return SAME_DEVICE_ERROR
    if meter is not None and (meter.device_group_id or meter.device_id) in device_ids:
        return SELF_METER_ERROR
    return None
