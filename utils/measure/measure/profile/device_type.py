from enum import StrEnum


class ProfileDeviceType(StrEnum):
    """Library device types available without importing the HA integration."""

    GENERIC_IOT = "generic_iot"
    AIR_CONDITIONER = "air_conditioner"
    AIR_PURIFIER = "air_purifier"
    CAMERA = "camera"
    COVER = "cover"
    FAN = "fan"
    HEATING = "heating"
    HUMIDIFIER = "humidifier"
    LAWN_MOWER_ROBOT = "lawn_mower_robot"
    LIGHT = "light"
    NETWORK = "network"
    POWER_METER = "power_meter"
    PRINTER = "printer"
    SET_TOP_BOX = "set_top_box"
    SMART_DIMMER = "smart_dimmer"
    SMART_SPEAKER = "smart_speaker"
    SMART_SWITCH = "smart_switch"
    TELEVISION = "television"
    UPS = "ups"
    VACUUM_ROBOT = "vacuum_robot"
    WATER_HEATER = "water_heater"


# Keep aligned with DEVICE_TYPE_DOMAIN in the Powercalc integration. The measure
# utility runs independently of Home Assistant and cannot import that module.
PROFILE_DEVICE_DOMAINS: dict[ProfileDeviceType, tuple[str, ...]] = {
    ProfileDeviceType.AIR_CONDITIONER: ("climate",),
    ProfileDeviceType.AIR_PURIFIER: ("fan",),
    ProfileDeviceType.CAMERA: ("camera",),
    ProfileDeviceType.COVER: ("cover",),
    ProfileDeviceType.FAN: ("fan",),
    ProfileDeviceType.GENERIC_IOT: ("media_player", "sensor"),
    ProfileDeviceType.LIGHT: ("light",),
    ProfileDeviceType.POWER_METER: ("sensor",),
    ProfileDeviceType.SET_TOP_BOX: ("media_player",),
    ProfileDeviceType.SMART_DIMMER: ("light",),
    ProfileDeviceType.SMART_SWITCH: ("light", "switch"),
    ProfileDeviceType.SMART_SPEAKER: ("media_player",),
    ProfileDeviceType.TELEVISION: ("media_player",),
    ProfileDeviceType.NETWORK: ("binary_sensor",),
    ProfileDeviceType.PRINTER: ("sensor",),
    ProfileDeviceType.VACUUM_ROBOT: ("vacuum",),
    ProfileDeviceType.LAWN_MOWER_ROBOT: ("lawn_mower",),
    ProfileDeviceType.HEATING: ("climate",),
    ProfileDeviceType.HUMIDIFIER: ("humidifier",),
    ProfileDeviceType.UPS: ("sensor",),
    ProfileDeviceType.WATER_HEATER: ("water_heater",),
}
