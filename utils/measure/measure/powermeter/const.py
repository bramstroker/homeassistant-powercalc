from enum import StrEnum


class PowerMeterType(StrEnum):
    DUMMY = "dummy"
    HASS = "hass"
    KASA = "kasa"
    MANUAL = "manual"
    OCR = "ocr"
    SHELLY = "shelly"
    TASMOTA = "tasmota"
    TUYA = "tuya"
    MYSTROM = "mystrom"


QUESTION_POWERMETER_ENTITY_ID = "powermeter_entity_id"
QUESTION_VOLTAGEMETER_ENTITY_ID = "voltagemeter_entity_id"

SHELLY_INFO_ENDPOINT = "/shelly"
SHELLY_GEN1_STATUS_ENDPOINT = "/status"
SHELLY_GEN2_SWITCH_STATUS_ENDPOINT = "/rpc/Switch.GetStatus?id=0"
SHELLY_GEN2_PM1_STATUS_ENDPOINT = "/rpc/PM1.GetStatus?id=0"
SHELLY_GEN2_STATUS_ENDPOINTS = (SHELLY_GEN2_SWITCH_STATUS_ENDPOINT, SHELLY_GEN2_PM1_STATUS_ENDPOINT)
