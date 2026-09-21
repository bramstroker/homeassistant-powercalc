from measure.controller.light.effects import filter_recordable_effects

ZIGBEE2MQTT_DEVICE = {
    "identifiers": [["mqtt", "zigbee2mqtt_0x0017880102030405"]],
}


def test_zigbee2mqtt_effect_filter_keeps_only_sustained_effects() -> None:
    effects = [
        "blink",
        "breathe",
        "okay",
        "channel_change",
        "finish_effect",
        "stop_effect",
        "stop_colorloop",
        "colorloop",
    ]

    assert filter_recordable_effects(effects, integration="mqtt", device=ZIGBEE2MQTT_DEVICE) == ["colorloop"]


def test_effect_filter_preserves_names_for_other_devices() -> None:
    effects = ["breathe", "stop_effect", "colorloop"]

    assert filter_recordable_effects(effects, integration="hue", device={}) == effects
    assert filter_recordable_effects(effects, integration="mqtt", device={}) == effects


def test_effect_filter_preserves_names_when_registry_metadata_is_malformed() -> None:
    effects = ["breathe", "stop_effect"]

    assert filter_recordable_effects(effects, integration="mqtt", device={"identifiers": None}) == effects


def test_zigbee2mqtt_effect_filter_handles_only_excluded_commands() -> None:
    effects = ["blink", "finish_effect", "stop_colorloop"]

    assert filter_recordable_effects(effects, integration="mqtt", device=ZIGBEE2MQTT_DEVICE) == []
