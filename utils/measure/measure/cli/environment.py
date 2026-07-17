import logging
from typing import Any

from decouple import Choices, UndefinedValueError, config

from measure.const import CT_BRI_STEPS_MANUAL, CT_MIRED_STEPS_MANUAL, PARAMETER_LIMITS, parse_measure_type
from measure.controller.charging.const import ChargingControllerType
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import DEFAULT_LIGHT_TRANSITION_TIME, LightControllerType
from measure.controller.media.const import MediaControllerType
from measure.powermeter.const import PowerMeterType
from measure.tuning import MeasurementParameters

_LOGGER = logging.getLogger("measure")

# Shared tuning defaults; the environment variables below only override these.
_DEFAULTS = MeasurementParameters()


def _clamp(name: str, value: float) -> Any:  # noqa: ANN401  # int env values must stay int; typing per call site
    minimum, maximum = PARAMETER_LIMITS[name]
    if minimum <= value <= maximum:
        return value
    clamped = min(max(value, minimum), maximum)
    _LOGGER.warning(
        "%s=%s is outside the allowed range [%s, %s]; using %s",
        name.upper(),
        value,
        minimum,
        maximum,
        clamped,
    )
    return clamped


def _bounded(name: str, *, cast: type = int) -> Any:  # noqa: ANN401  # int env values must stay int; typing per call site
    """Read the env override (NAME uppercased), fall back to the shared tuning default, clamp to the table."""
    return _clamp(name, config(name.upper(), default=getattr(_DEFAULTS, name), cast=cast))


class CliEnvironment:
    @property
    def min_brightness(self) -> int:
        return _clamp(
            "min_brightness",
            config(
                "MIN_BRIGHTNESS",
                default=config("START_BRIGHTNESS", default=_DEFAULTS.min_brightness, cast=int),
                cast=int,
            ),
        )

    @property
    def max_brightness(self) -> int:
        return _DEFAULTS.max_brightness

    @property
    def min_sat(self) -> int:
        return _bounded("min_sat")

    @property
    def max_sat(self) -> int:
        return _bounded("max_sat")

    @property
    def min_hue(self) -> int:
        return _bounded("min_hue")

    @property
    def max_hue(self) -> int:
        return _bounded("max_hue")

    @property
    def ct_bri_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return CT_BRI_STEPS_MANUAL
        return _bounded("ct_bri_steps")

    @property
    def ct_mired_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return CT_MIRED_STEPS_MANUAL
        return _bounded("ct_mired_steps")

    @property
    def bri_bri_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 3
        return 1

    @property
    def hs_bri_precision(self) -> float:
        hs_bri_precision = config("HS_BRI_PRECISION", default=1, cast=float)
        hs_bri_precision = min(hs_bri_precision, 4)
        return max(hs_bri_precision, 0.5)

    @property
    def hs_bri_steps(self) -> int:
        return round(32 / self.hs_bri_precision)

    @property
    def hs_hue_precision(self) -> float:
        hs_hue_precision = config("HS_HUE_PRECISION", default=1, cast=float)
        hs_hue_precision = min(hs_hue_precision, 4)
        return max(hs_hue_precision, 0.5)

    @property
    def hs_hue_steps(self) -> int:
        return round(2731 / self.hs_hue_precision)

    @property
    def hs_sat_precision(self) -> float:
        hs_sat_precision = config("HS_SAT_PRECISION", default=1, cast=float)
        hs_sat_precision = min(hs_sat_precision, 4)
        return max(hs_sat_precision, 0.5)

    @property
    def hs_sat_steps(self) -> int:
        return round(32 / self.hs_sat_precision)

    @property
    def effect_bri_steps(self) -> int:
        return _bounded("effect_bri_steps")

    @property
    def selected_light_controller(self) -> LightControllerType:
        return config(
            "LIGHT_CONTROLLER",
            cast=Choices([t.value for t in LightControllerType]),
            default=LightControllerType.HASS.value,
        )

    @property
    def selected_media_controller(self) -> MediaControllerType:
        return config(
            "MEDIA_CONTROLLER",
            cast=Choices([t.value for t in MediaControllerType]),
            default=MediaControllerType.HASS.value,
        )

    @property
    def selected_charging_controller(self) -> ChargingControllerType:
        return config(
            "CHARGING_CONTROLLER",
            cast=Choices([t.value for t in ChargingControllerType]),
            default=ChargingControllerType.HASS.value,
        )

    @property
    def selected_fan_controller(self) -> FanControllerType:
        return config(
            "FAN_CONTROLLER",
            cast=Choices([t.value for t in FanControllerType]),
            default=FanControllerType.HASS.value,
        )

    @property
    def selected_power_meter(self) -> PowerMeterType:
        return config(
            "POWER_METER",
            cast=Choices([t.value for t in PowerMeterType]),
            default=PowerMeterType.HASS.value,
        )

    @property
    def log_level(self) -> int:
        return config("LOG_LEVEL", default=logging.INFO)

    @property
    def sleep_initial(self) -> int:
        return _bounded("sleep_initial")

    @property
    def sleep_standby(self) -> int:
        return _bounded("sleep_standby")

    @property
    def sleep_time(self) -> float:
        return _bounded("sleep_time", cast=float)

    @property
    def sleep_time_sample(self) -> int:
        return _bounded("sleep_time_sample")

    @property
    def sleep_time_hue(self) -> int:
        return config("SLEEP_TIME_HUE", default=_DEFAULTS.sleep_time_hue, cast=int)

    @property
    def sleep_time_sat(self) -> int:
        return config("SLEEP_TIME_SAT", default=_DEFAULTS.sleep_time_sat, cast=int)

    @property
    def sleep_time_ct(self) -> int:
        return config("SLEEP_TIME_CT", default=_DEFAULTS.sleep_time_ct, cast=int)

    @property
    def measure_time_effect(self) -> int:
        """Maximum seconds to measure each effect/brightness combination."""
        return _bounded("measure_time_effect")

    @property
    def measure_time_effect_min(self) -> int:
        """Minimum seconds before effect measurement can stop on convergence."""
        return min(_bounded("measure_time_effect_min"), self.measure_time_effect)

    @property
    def measure_time_effect_convergence_window(self) -> int:
        """Seconds between cumulative-average snapshots used for convergence checks."""
        return min(
            config(
                "MEASURE_TIME_EFFECT_CONVERGENCE_WINDOW",
                default=_DEFAULTS.measure_time_effect_convergence_window,
                cast=int,
            ),
            self.measure_time_effect_min,
        )

    @property
    def measure_time_effect_convergence_abs(self) -> float:
        """Maximum watt change allowed for effect average convergence."""
        return config(
            "MEASURE_TIME_EFFECT_CONVERGENCE_ABS",
            default=_DEFAULTS.measure_time_effect_convergence_abs,
            cast=float,
        )

    @property
    def measure_time_effect_convergence_rel(self) -> float:
        """Maximum percentage change allowed for effect average convergence."""
        return (
            config(
                "MEASURE_TIME_EFFECT_CONVERGENCE_REL",
                default=_DEFAULTS.measure_time_effect_convergence_rel * 100,
                cast=float,
            )
            / 100
        )

    @property
    def sleep_time_effect_change(self) -> int:
        return config("SLEEP_TIME_EFFECT_CHANGE", default=_DEFAULTS.sleep_time_effect_change, cast=int)

    @property
    def sleep_time_nudge(self) -> float:
        return config("SLEEP_TIME_NUDGE", default=_DEFAULTS.sleep_time_nudge, cast=float)

    @property
    def pulse_time_nudge(self) -> float:
        return config("PULSE_TIME_NUDGE", default=_DEFAULTS.pulse_time_nudge, cast=float)

    @property
    def max_retries(self) -> int:
        return _bounded("max_retries")

    @property
    def max_nudges(self) -> int:
        return _bounded("max_nudges")

    @property
    def sample_count(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 1
        return _bounded("sample_count")

    @property
    def selected_measure_type(self) -> str | None:
        try:
            return parse_measure_type(config("SELECTED_MEASURE_TYPE"))
        except UndefinedValueError:
            return None

    @property
    def resume(self) -> bool:
        return config("RESUME", default=True, cast=bool)

    @property
    def prompt_resume(self) -> bool:
        return True

    @property
    def shelly_ip(self) -> str:
        return config("SHELLY_IP")

    @property
    def shelly_timeout(self) -> int:
        return config("SHELLY_TIMEOUT", default=5, cast=int)

    @property
    def tuya_device_id(self) -> str:
        return config("TUYA_DEVICE_ID")

    @property
    def tuya_device_ip(self) -> str:
        return config("TUYA_DEVICE_IP")

    @property
    def tuya_device_key(self) -> str:
        return config("TUYA_DEVICE_KEY")

    @property
    def tuya_device_version(self) -> str:
        return config("TUYA_DEVICE_VERSION", default="3.3")

    @property
    def hue_bridge_ip(self) -> str:
        return config("HUE_BRIDGE_IP")

    @property
    def hass_url(self) -> str:
        return config("HASS_URL")

    @property
    def hass_token(self) -> str:
        return config("HASS_TOKEN")

    @property
    def hass_call_update_entity_service(self) -> bool:
        return config(
            "HASS_CALL_UPDATE_ENTITY_SERVICE",
            default=False,
            cast=bool,
        )

    @property
    def light_transition_time(self) -> int:
        return config(
            "LIGHT_TRANSITION_TIME",
            default=DEFAULT_LIGHT_TRANSITION_TIME,
            cast=int,
        )

    @property
    def tasmota_device_ip(self) -> str:
        return config("TASMOTA_DEVICE_IP")

    @property
    def kasa_device_ip(self) -> str:
        return config("KASA_DEVICE_IP")

    @property
    def mystrom_device_ip(self) -> str:
        return config("MYSTROM_DEVICE_IP")

    @property
    def csv_add_datetime_column(self) -> bool:
        return config("CSV_ADD_DATETIME_COLUMN", default=_DEFAULTS.csv_add_datetime_column, cast=bool)

    @staticmethod
    def get_conf_value(key: str) -> str | None:
        """Get configuration value from environment variable"""
        return config(key, default=None)
