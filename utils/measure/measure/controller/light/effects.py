from collections.abc import Mapping, Sequence

from measure.home_assistant.connectivity import is_zigbee2mqtt_device

ZIGBEE2MQTT_TRANSIENT_EFFECTS = frozenset(
    {
        "blink",
        "breathe",
        "channel_change",
        "okay",
    }
)
ZIGBEE2MQTT_STOP_EFFECTS = frozenset(
    {
        "finish_effect",
        "stop_colorloop",
        "stop_effect",
    }
)
ZIGBEE2MQTT_UNRECORDABLE_EFFECTS = ZIGBEE2MQTT_TRANSIENT_EFFECTS | ZIGBEE2MQTT_STOP_EFFECTS


def filter_recordable_effects(
    effects: Sequence[str],
    *,
    integration: str | None,
    device: Mapping[str, object],
) -> list[str]:
    """Remove commands that do not represent sustained Zigbee2MQTT operating modes."""

    if not is_zigbee2mqtt_device(integration, device):
        return list(effects)
    return [effect for effect in effects if effect.casefold() not in ZIGBEE2MQTT_UNRECORDABLE_EFFECTS]
