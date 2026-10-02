"""Model JSON fields for fixed self-consumption profiles."""

from typing import Any

from measure.profile.device_type import ProfileDeviceType
from measure.profile.standby import MINIMUM_STANDBY_POWER


class UnusableSelfConsumptionError(ValueError):
    """The measured self consumption cannot be published as a fixed profile."""


def create_fixed_profile_data(device_type: ProfileDeviceType, power: float) -> dict[str, Any]:
    """Build fixed-profile fields from the measured average, rejecting values the library cannot use."""
    power = round(power, 4)
    is_power_meter = device_type == ProfileDeviceType.POWER_METER
    if power <= 0:
        raise UnusableSelfConsumptionError(
            f"Measured {power} W, but a fixed profile needs positive self consumption; check the meter and device"
        )
    if is_power_meter and power < MINIMUM_STANDBY_POWER:
        raise UnusableSelfConsumptionError(
            f"Measured {power} W, but power meter self consumption must be at least {MINIMUM_STANDBY_POWER} W "
            "for a valid profile"
        )

    data: dict[str, Any] = {
        "device_type": device_type.value,
        "calculation_strategy": "fixed",
        "discovery_by": "device",
    }
    if is_power_meter:
        data["standby_power"] = power
        data["only_self_usage"] = True
    else:
        data["fixed_config"] = {"power": power}
    return data
