from collections.abc import Callable
from enum import StrEnum
import logging
from typing import Any, cast, overload

from decouple import Choices, UndefinedValueError, config

from measure.const import CT_BRI_STEPS_MANUAL, CT_MIRED_STEPS_MANUAL, PARAMETER_LIMITS, MeasureType, parse_measure_type
from measure.controller.charging.const import ChargingControllerType
from measure.controller.fan.const import FanControllerType
from measure.controller.light.const import DEFAULT_LIGHT_TRANSITION_TIME, LightControllerType
from measure.controller.media.const import MediaControllerType
from measure.powermeter.const import PowerMeterType
from measure.tuning import MeasurementParameters

_LOGGER = logging.getLogger("measure")

# Shared tuning defaults; the environment variables below only override these.
_DEFAULTS = MeasurementParameters()
_UNSET = object()


def _config_value[T](
    key: str,
    *,
    converter: Callable[[Any], T],
    default: object = _UNSET,
) -> T:
    if default is _UNSET:
        return cast(T, config(key, cast=converter))
    return cast(T, config(key, default=default, cast=converter))


def _enum_value[T: StrEnum](key: str, enum_type: type[T], default: T) -> T:
    choices = Choices([item.value for item in enum_type])
    return _config_value(
        key,
        converter=lambda value: enum_type(choices(value)),
        default=default.value,
    )


@overload
def _clamp(name: str, value: int) -> int: ...


@overload
def _clamp(name: str, value: float) -> float: ...


def _clamp(name: str, value: float) -> int | float:
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
    return int(clamped) if isinstance(value, int) else float(clamped)


def _bounded_int(name: str) -> int:
    """Read the env override (NAME uppercased), fall back to the shared tuning default, clamp to the table."""
    value = _config_value(name.upper(), default=getattr(_DEFAULTS, name), converter=int)
    return _clamp(name, value)


def _bounded_float(name: str) -> float:
    value = _config_value(name.upper(), default=getattr(_DEFAULTS, name), converter=float)
    return _clamp(name, value)


class CliEnvironment:
    @property
    def min_brightness(self) -> int:
        return _clamp(
            "min_brightness",
            _config_value(
                "MIN_BRIGHTNESS",
                default=_config_value("START_BRIGHTNESS", default=_DEFAULTS.min_brightness, converter=int),
                converter=int,
            ),
        )

    @property
    def max_brightness(self) -> int:
        return _DEFAULTS.max_brightness

    @property
    def min_sat(self) -> int:
        return _bounded_int("min_sat")

    @property
    def max_sat(self) -> int:
        return _bounded_int("max_sat")

    @property
    def min_hue(self) -> int:
        return _bounded_int("min_hue")

    @property
    def max_hue(self) -> int:
        return _bounded_int("max_hue")

    @property
    def ct_bri_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return CT_BRI_STEPS_MANUAL
        return _bounded_int("ct_bri_steps")

    @property
    def ct_mired_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return CT_MIRED_STEPS_MANUAL
        return _bounded_int("ct_mired_steps")

    @property
    def bri_bri_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 3
        return 1

    @property
    def hs_bri_precision(self) -> float:
        hs_bri_precision = _config_value("HS_BRI_PRECISION", default=1, converter=float)
        hs_bri_precision = min(hs_bri_precision, 4)
        return max(hs_bri_precision, 0.5)

    @property
    def hs_bri_steps(self) -> int:
        return round(32 / self.hs_bri_precision)

    @property
    def hs_hue_precision(self) -> float:
        hs_hue_precision = _config_value("HS_HUE_PRECISION", default=1, converter=float)
        hs_hue_precision = min(hs_hue_precision, 4)
        return max(hs_hue_precision, 0.5)

    @property
    def hs_hue_steps(self) -> int:
        return round(2731 / self.hs_hue_precision)

    @property
    def hs_sat_precision(self) -> float:
        hs_sat_precision = _config_value("HS_SAT_PRECISION", default=1, converter=float)
        hs_sat_precision = min(hs_sat_precision, 4)
        return max(hs_sat_precision, 0.5)

    @property
    def hs_sat_steps(self) -> int:
        return round(32 / self.hs_sat_precision)

    @property
    def effect_bri_steps(self) -> int:
        return _bounded_int("effect_bri_steps")

    @property
    def selected_light_controller(self) -> LightControllerType:
        return _enum_value("LIGHT_CONTROLLER", LightControllerType, LightControllerType.HASS)

    @property
    def selected_media_controller(self) -> MediaControllerType:
        return _enum_value("MEDIA_CONTROLLER", MediaControllerType, MediaControllerType.HASS)

    @property
    def selected_charging_controller(self) -> ChargingControllerType:
        return _enum_value("CHARGING_CONTROLLER", ChargingControllerType, ChargingControllerType.HASS)

    @property
    def selected_fan_controller(self) -> FanControllerType:
        return _enum_value("FAN_CONTROLLER", FanControllerType, FanControllerType.HASS)

    @property
    def selected_power_meter(self) -> PowerMeterType:
        return _enum_value("POWER_METER", PowerMeterType, PowerMeterType.HASS)

    @property
    def log_level(self) -> str:
        return _config_value("LOG_LEVEL", default=logging.getLevelName(logging.INFO), converter=str)

    @property
    def sleep_initial(self) -> int:
        return _bounded_int("sleep_initial")

    @property
    def sleep_standby(self) -> int:
        return _bounded_int("sleep_standby")

    @property
    def sleep_time(self) -> float:
        return _bounded_float("sleep_time")

    @property
    def sleep_time_sample(self) -> int:
        return _bounded_int("sleep_time_sample")

    @property
    def sleep_time_hue(self) -> int:
        return _config_value("SLEEP_TIME_HUE", default=_DEFAULTS.sleep_time_hue, converter=int)

    @property
    def sleep_time_sat(self) -> int:
        return _config_value("SLEEP_TIME_SAT", default=_DEFAULTS.sleep_time_sat, converter=int)

    @property
    def sleep_time_ct(self) -> int:
        return _config_value("SLEEP_TIME_CT", default=_DEFAULTS.sleep_time_ct, converter=int)

    @property
    def measure_time_effect(self) -> int:
        """Maximum seconds to measure each effect/brightness combination."""
        return _bounded_int("measure_time_effect")

    @property
    def measure_time_effect_min(self) -> int:
        """Minimum seconds before effect measurement can stop on convergence."""
        return min(_bounded_int("measure_time_effect_min"), self.measure_time_effect)

    @property
    def measure_time_effect_convergence_window(self) -> int:
        """Seconds between cumulative-average snapshots used for convergence checks."""
        return min(
            _config_value(
                "MEASURE_TIME_EFFECT_CONVERGENCE_WINDOW",
                default=_DEFAULTS.measure_time_effect_convergence_window,
                converter=int,
            ),
            self.measure_time_effect_min,
        )

    @property
    def measure_time_effect_convergence_abs(self) -> float:
        """Maximum watt change allowed for effect average convergence."""
        return _config_value(
            "MEASURE_TIME_EFFECT_CONVERGENCE_ABS",
            default=_DEFAULTS.measure_time_effect_convergence_abs,
            converter=float,
        )

    @property
    def measure_time_effect_convergence_rel(self) -> float:
        """Maximum percentage change allowed for effect average convergence."""
        return (
            _config_value(
                "MEASURE_TIME_EFFECT_CONVERGENCE_REL",
                default=_DEFAULTS.measure_time_effect_convergence_rel * 100,
                converter=float,
            )
            / 100
        )

    @property
    def sleep_time_effect_change(self) -> int:
        return _config_value("SLEEP_TIME_EFFECT_CHANGE", default=_DEFAULTS.sleep_time_effect_change, converter=int)

    @property
    def sleep_time_nudge(self) -> float:
        return _config_value("SLEEP_TIME_NUDGE", default=_DEFAULTS.sleep_time_nudge, converter=float)

    @property
    def pulse_time_nudge(self) -> float:
        return _config_value("PULSE_TIME_NUDGE", default=_DEFAULTS.pulse_time_nudge, converter=float)

    @property
    def max_retries(self) -> int:
        return _bounded_int("max_retries")

    @property
    def max_nudges(self) -> int:
        return _bounded_int("max_nudges")

    @property
    def fast_test_mode(self) -> bool:
        """Fast test mode is controlled by the developer-only app setting."""
        return False

    @property
    def sample_count(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 1
        return _bounded_int("sample_count")

    @property
    def selected_measure_type(self) -> MeasureType | None:
        try:
            return parse_measure_type(_config_value("SELECTED_MEASURE_TYPE", converter=str))
        except UndefinedValueError:
            return None

    @property
    def resume(self) -> bool:
        return _config_value("RESUME", default=True, converter=bool)

    @property
    def prompt_resume(self) -> bool:
        return True

    @property
    def shelly_ip(self) -> str:
        return _config_value("SHELLY_IP", converter=str)

    @property
    def shelly_timeout(self) -> int:
        return _config_value("SHELLY_TIMEOUT", default=5, converter=int)

    @property
    def tuya_device_id(self) -> str:
        return _config_value("TUYA_DEVICE_ID", converter=str)

    @property
    def tuya_device_ip(self) -> str:
        return _config_value("TUYA_DEVICE_IP", converter=str)

    @property
    def tuya_device_key(self) -> str:
        return _config_value("TUYA_DEVICE_KEY", converter=str)

    @property
    def tuya_device_version(self) -> str:
        return _config_value("TUYA_DEVICE_VERSION", default="3.3", converter=str)

    @property
    def hue_bridge_ip(self) -> str:
        return _config_value("HUE_BRIDGE_IP", converter=str)

    @property
    def hass_url(self) -> str:
        return _config_value("HASS_URL", converter=str)

    @property
    def hass_token(self) -> str:
        return _config_value("HASS_TOKEN", converter=str)

    @property
    def hass_call_update_entity_service(self) -> bool:
        return _config_value(
            "HASS_CALL_UPDATE_ENTITY_SERVICE",
            default=False,
            converter=bool,
        )

    @property
    def light_transition_time(self) -> int:
        return _config_value(
            "LIGHT_TRANSITION_TIME",
            default=DEFAULT_LIGHT_TRANSITION_TIME,
            converter=int,
        )

    @property
    def tasmota_device_ip(self) -> str:
        return _config_value("TASMOTA_DEVICE_IP", converter=str)

    @property
    def kasa_device_ip(self) -> str:
        return _config_value("KASA_DEVICE_IP", converter=str)

    @property
    def mystrom_device_ip(self) -> str:
        return _config_value("MYSTROM_DEVICE_IP", converter=str)

    @property
    def csv_add_datetime_column(self) -> bool:
        return _config_value(
            "CSV_ADD_DATETIME_COLUMN",
            default=_DEFAULTS.csv_add_datetime_column,
            converter=bool,
        )

    @staticmethod
    def get_conf_value(key: str) -> str | None:
        """Get configuration value from environment variable"""
        return cast(str | None, config(key, default=None))
