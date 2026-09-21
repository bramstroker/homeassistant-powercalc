"""Registry examples matching HA Hue/deCONZ and Zigbee2MQTT discovery payloads."""

from measure.home_assistant.connectivity import detect_connectivity
import pytest

IEEE = "00:17:88:01:02:03:04:05"


@pytest.mark.parametrize(
    "integration,device,expected",
    [
        ("zha", {}, "zigbee"),
        ("zwave_js", {}, "zwave"),
        ("mqtt", {"identifiers": [["mqtt", "zigbee2mqtt_0x0017880102030405"]]}, "zigbee"),
        ("mqtt", {"identifiers": [["mqtt", "zigbee2mqtt_0x001788AABBCCDDEE"]]}, "zigbee"),
        ("deconz", {"connections": [["zigbee", IEEE]]}, "zigbee"),
        ("hue", {"identifiers": [["hue", f"{IEEE}-0b"]], "via_device_id": "bridge"}, "zigbee"),
        ("hue", {"identifiers": [["hue", IEEE]], "via_device_id": "bridge"}, "zigbee"),
        ("hue", {"connections": [["mac", IEEE]], "via_device_id": "bridge"}, "zigbee"),
        ("zha", {"connections": [["zigbee", IEEE], ["mac", "00:11:22:33:44:55"]]}, "zigbee"),
        ("zwave_js", {"identifiers": [["zwave_js", "123-4"]]}, "zwave"),
        (None, {}, None),
        ("", {}, None),
        ("mqtt", {}, None),
        ("mqtt", {"manufacturer": "Zigbee2MQTT", "name": "Zigbee light"}, None),
        ("mqtt", {"identifiers": [["mqtt", "zigbee2mqtt_bridge_0x0017880102030405"]]}, None),
        ("mqtt", {"identifiers": [["mqtt", "zigbee2mqtt_kitchen_1"]]}, None),
        ("mqtt", {"identifiers": [["mqtt", "zigbee2mqtt_0x1234"]]}, None),
        ("mqtt", {"identifiers": [["other", "zigbee2mqtt_0x0017880102030405"]]}, None),
        ("mqtt", {"identifiers": [["mqtt", "prefix_zigbee2mqtt_0x0017880102030405"]]}, None),
        ("hue", {"connections": [["mac", "00:11:22:33:44:55"]], "via_device_id": "bridge"}, None),
        ("hue", {"connections": [["mac", IEEE]]}, None),
        ("hue", {"connections": [["mac", IEEE]], "via_device_id": ""}, None),
        ("hue", {"connections": [["mac", IEEE]], "via_device_id": 42}, None),
        ("hue", {"identifiers": [["hue", "room-uuid"]], "via_device_id": "bridge"}, None),
        ("hue", {"identifiers": [["hue", "00:11:22:33:44:55-0b"]], "via_device_id": "bridge"}, None),
        ("hue", {"identifiers": [["other", f"{IEEE}-0b"]], "via_device_id": "bridge"}, None),
        ("hue", {"connections": [["other", IEEE]], "via_device_id": "bridge"}, None),
        ("hue", {"connections": [["mac", IEEE]], "via_device_id": "bridge", "entry_type": "service"}, None),
        ("zha", {"entry_type": "service"}, None),
        ("deconz", {}, None),
        ("deconz", {"connections": [["mac", IEEE]]}, None),
        ("deconz", {"connections": [["zigbee", "invalid"]]}, None),
        ("matter", {"connections": [["zigbee", IEEE]]}, None),
        ("shelly", {"connections": [["mac", "00:11:22:33:44:55"]]}, None),
        ("tuya", {}, None),
        ("esphome", {}, None),
        ("zwave_js", {"connections": [["zigbee", IEEE]]}, None),
        ("zha", {"connections": [["bluetooth", "00:11:22:33:44:55"]]}, None),
        ("zha", {"identifiers": [["zwave_js", "123-4"]]}, None),
        ("mqtt", {"identifiers": [["mqtt", "zigbee2mqtt_0x0017880102030405"], ["zwave_js", "123-4"]]}, None),
    ],
)
def test_detect_connectivity(integration: str | None, device: dict[str, object], expected: str | None) -> None:
    assert detect_connectivity(integration, device) == expected


@pytest.mark.parametrize("field", ["identifiers", "connections"])
@pytest.mark.parametrize(
    "value", [None, {}, "zigbee", [None], [["zigbee"]], [["zigbee", 42]], [["", "id"]], [["id", ""]]]
)
def test_malformed_registry_metadata_is_not_used(field: str, value: object) -> None:
    assert detect_connectivity("zha", {field: value}) is None
