from enum import Enum


class PowerMeterType(str, Enum):
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


class Trend(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STEADY = "steady"


dummy_load_measurement_count = 20
dummy_load_measurements_duration = 30
