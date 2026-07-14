from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from measure.home_assistant import HomeAssistantManager
from measure.powermeter.hass import HassPowerMeter


def test_autodetects_voltage_sensor_on_same_device() -> None:
    client = MagicMock(spec=HomeAssistantManager)
    client.list_entity_registry.return_value = (
        SimpleNamespace(entity_id="sensor.workbench_consumption", device_id="plug-device"),
        SimpleNamespace(entity_id="sensor.mains_potential", device_id="plug-device"),
        SimpleNamespace(entity_id="sensor.other_voltage", device_id="other-device"),
    )
    meter = HassPowerMeter(client, False)

    with (
        patch.object(meter, "get_power_sensors", return_value=["sensor.workbench_consumption"]),
        patch.object(
            meter,
            "get_voltage_sensors",
            return_value=["sensor.mains_potential", "sensor.other_voltage"],
        ),
    ):
        assert meter.autodetect_voltage_entity("sensor.workbench_consumption") is True
        assert meter.match_power_and_voltage_sensors() == {
            "sensor.workbench_consumption": "sensor.mains_potential",
        }
