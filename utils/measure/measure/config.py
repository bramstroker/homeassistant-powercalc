import logging

from decouple import Choices, UndefinedValueError, config

from measure.controller.charging.const import ChargingControllerType
from measure.controller.light.const import LightControllerType
from measure.controller.media.const import MediaControllerType
from measure.powermeter.const import PowerMeterType

MIN_BRIGHTNESS = min(
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
MAX_BRIGHTNESS = 255
MIN_SAT = min(max(config("MIN_SAT", default=1, cast=int), 1), 255)
MAX_SAT = min(max(config("MAX_SAT", default=255, cast=int), 1), 255)
MIN_HUE = min(max(config("MIN_HUE", default=1, cast=int), 1), 65535)
MAX_HUE = min(max(config("MAX_HUE", default=65535, cast=int), 1), 65535)
CT_BRI_STEPS = min(config("CT_BRI_STEPS", default=5, cast=int), 10)
CT_MIRED_STEPS = min(config("CT_MIRED_STEPS", default=10, cast=int), 10)
BRI_BRI_STEPS = 1

HS_BRI_PRECISION = config("HS_BRI_PRECISION", default=1, cast=float)
HS_BRI_PRECISION = min(HS_BRI_PRECISION, 4)
HS_BRI_PRECISION = max(HS_BRI_PRECISION, 0.5)
HS_BRI_STEPS = round(32 / HS_BRI_PRECISION)
del HS_BRI_PRECISION

HS_HUE_PRECISION = config("HS_HUE_PRECISION", default=1, cast=float)
HS_HUE_PRECISION = min(HS_HUE_PRECISION, 4)
HS_HUE_PRECISION = max(HS_HUE_PRECISION, 0.5)
HS_HUE_STEPS = round(2731 / HS_HUE_PRECISION)
del HS_HUE_PRECISION

HS_SAT_PRECISION = config("HS_SAT_PRECISION", default=1, cast=float)
HS_SAT_PRECISION = min(HS_SAT_PRECISION, 4)
HS_SAT_PRECISION = max(HS_SAT_PRECISION, 0.5)
HS_SAT_STEPS = round(32 / HS_SAT_PRECISION)
del HS_SAT_PRECISION

SELECTED_LIGHT_CONTROLLER = config(
    "LIGHT_CONTROLLER",
    cast=Choices([t.value for t in LightControllerType]),
    default=LightControllerType.HASS.value,
)
SELECTED_MEDIA_CONTROLLER = config(
    "MEDIA_CONTROLLER",
    cast=Choices([t.value for t in MediaControllerType]),
    default=MediaControllerType.HASS.value,
)
SELECTED_CHARGING_CONTROLLER = config(
    "CHARGING_CONTROLLER",
    cast=Choices([t.value for t in ChargingControllerType]),
    default=ChargingControllerType.HASS.value,
)
SELECTED_POWER_METER = config(
    "POWER_METER",
    cast=Choices([t.value for t in PowerMeterType]),
)

LOG_LEVEL = config("LOG_LEVEL", default=logging.INFO)
SLEEP_INITIAL = 10
SLEEP_STANDBY = config("SLEEP_STANDBY", default=20, cast=int)
SLEEP_TIME = config("SLEEP_TIME", default=2, cast=int)
SLEEP_TIME_SAMPLE = config("SLEEP_TIME_SAMPLE", default=1, cast=int)
SLEEP_TIME_HUE = config("SLEEP_TIME_HUE", default=5, cast=int)
SLEEP_TIME_SAT = config("SLEEP_TIME_SAT", default=10, cast=int)
SLEEP_TIME_CT = config("SLEEP_TIME_CT", default=10, cast=int)
SLEEP_TIME_NUDGE = config("SLEEP_TIME_NUDGE", default=10, cast=float)

PULSE_TIME_NUDGE = config("PULSE_TIME_NUDGE", default=2, cast=float)
MAX_RETRIES = config("MAX_RETRIES", default=5, cast=int)
MAX_NUDGES = config("MAX_NUDGES", default=0, cast=int)
SAMPLE_COUNT = config("SAMPLE_COUNT", default=1, cast=int)

SHELLY_IP = config("SHELLY_IP")
SHELLY_TIMEOUT = config("SHELLY_TIMEOUT", default=5, cast=int)
TUYA_DEVICE_ID = config("TUYA_DEVICE_ID")
TUYA_DEVICE_IP = config("TUYA_DEVICE_IP")
TUYA_DEVICE_KEY = config("TUYA_DEVICE_KEY")
TUYA_DEVICE_VERSION = config("TUYA_DEVICE_VERSION", default="3.3")
HUE_BRIDGE_IP = config("HUE_BRIDGE_IP")
HASS_URL = config("HASS_URL")
HASS_TOKEN = config("HASS_TOKEN")
HASS_CALL_UPDATE_ENTITY_SERVICE = config(
    "HASS_CALL_UPDATE_ENTITY_SERVICE",
    default=False,
    cast=bool,
)
LIGHT_TRANSITION_TIME = config(
    "LIGHT_TRANSITION_TIME",
    default=0,
    cast=int,
)
TASMOTA_DEVICE_IP = config("TASMOTA_DEVICE_IP")
KASA_DEVICE_IP = config("KASA_DEVICE_IP")
MYSTROM_DEVICE_IP = config("MYSTROM_DEVICE_IP")

CSV_ADD_DATETIME_COLUMN = config("CSV_ADD_DATETIME_COLUMN", default=False, cast=bool)

try:
    SELECTED_MEASURE_TYPE = config("SELECTED_DEVICE_TYPE")
except UndefinedValueError:
    SELECTED_MEASURE_TYPE = None

try:
    RESUME = config("RESUME", cast=bool)
except UndefinedValueError:
    RESUME = None

# Change some settings when selected power meter is manual
if SELECTED_POWER_METER == PowerMeterType.MANUAL:
    SAMPLE_COUNT = 1
    BRI_BRI_STEPS = 3
    CT_BRI_STEPS = 15
    CT_MIRED_STEPS = 50
