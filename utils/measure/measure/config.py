import logging

from decouple import Choices, UndefinedValueError, config

from measure.const import MeasureType
from measure.controller.charging.const import ChargingControllerType
from measure.controller.light.const import LightControllerType
from measure.controller.media.const import MediaControllerType
from measure.powermeter.const import PowerMeterType


class MeasureConfig:
    @property
    def min_brightness(self) -> int:
        return min(
            max(
                config(
                    "MIN_BRIGHTNESS",
                    default=config("START_BRIGHTNESS", default=1, cast=int),
                    cast=int,
                ),
                1,
            ),
            255,
        )

    @property
    def max_brightness(self) -> int:
        return 255

    @property
    def min_sat(self) -> int:
        return min(max(config("MIN_SAT", default=1, cast=int), 1), 255)

    @property
    def max_sat(self) -> int:
        return min(max(config("MAX_SAT", default=255, cast=int), 1), 255)

    @property
    def min_hue(self) -> int:
        return min(max(config("MIN_HUE", default=1, cast=int), 1), 65535)

    @property
    def max_hue(self) -> int:
        return min(max(config("MAX_HUE", default=65535, cast=int), 1), 65535)

    @property
    def ct_bri_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 15
        return min(config("CT_BRI_STEPS", default=5, cast=int), 10)

    @property
    def ct_mired_steps(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 50
        return min(config("CT_MIRED_STEPS", default=10, cast=int), 10)

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
    def selected_power_meter(self) -> PowerMeterType:
        return config(
            "POWER_METER",
            cast=Choices([t.value for t in PowerMeterType]),
        )

    @property
    def log_level(self) -> int:
        return config("LOG_LEVEL", default=logging.INFO)

    @property
    def sleep_initial(self) -> int:
        return 10

    @property
    def sleep_standby(self) -> int:
        return config("SLEEP_STANDBY", default=20, cast=int)

    @property
    def sleep_time(self) -> int:
        return config("SLEEP_TIME", default=2, cast=int)

    @property
    def sleep_time_sample(self) -> int:
        return config("SLEEP_TIME_SAMPLE", default=1, cast=int)

    @property
    def sleep_time_hue(self) -> int:
        return config("SLEEP_TIME_HUE", default=5, cast=int)

    @property
    def sleep_time_sat(self) -> int:
        return config("SLEEP_TIME_SAT", default=10, cast=int)

    @property
    def sleep_time_ct(self) -> int:
        return config("SLEEP_TIME_CT", default=10, cast=int)

    @property
    def sleep_time_nudge(self) -> float:
        return config("SLEEP_TIME_NUDGE", default=10, cast=float)

    @property
    def pulse_time_nudge(self) -> float:
        return config("PULSE_TIME_NUDGE", default=2, cast=float)

    @property
    def max_retries(self) -> int:
        return config("MAX_RETRIES", default=5, cast=int)

    @property
    def max_nudges(self) -> int:
        return config("MAX_NUDGES", default=0, cast=int)

    @property
    def sample_count(self) -> int:
        if self.selected_power_meter == PowerMeterType.MANUAL:
            return 1
        return config("SAMPLE_COUNT", default=1, cast=int)

    @property
    def selected_measure_type(self) -> str | None:
        try:
            return MeasureType(config("SELECTED_DEVICE_TYPE", default=config("SELECTED_MEASURE_TYPE")))
        except UndefinedValueError:
            return None

    @property
    def resume(self) -> bool:
        try:
            return config("RESUME", cast=bool)
        except UndefinedValueError:
            return False

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
            default=0,
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
        return config("CSV_ADD_DATETIME_COLUMN", default=False, cast=bool)

    @staticmethod
    def get_conf_value(key: str) -> str | None:
        """Get configuration value from environment variable"""
        return config(key, default=None)
