import logging

from measure import config
from measure.powermeter.const import PowerMeterType
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.hass import HassPowerMeter
from measure.powermeter.kasa import KasaPowerMeter
from measure.powermeter.manual import ManualPowerMeter
from measure.powermeter.mystrom import MyStromPowerMeter
from measure.powermeter.ocr import OcrPowerMeter
from measure.powermeter.powermeter import PowerMeter
from measure.powermeter.shelly import ShellyPowerMeter
from measure.powermeter.tasmota import TasmotaPowerMeter
from measure.powermeter.tuya import TuyaPowerMeter

_LOGGER = logging.getLogger("measure")


class PowerMeterFactory:
    @staticmethod
    def dummy() -> DummyPowerMeter:
        return DummyPowerMeter()

    @staticmethod
    def hass() -> HassPowerMeter:
        return HassPowerMeter(
            config.HASS_URL,
            config.HASS_TOKEN,
            config.HASS_CALL_UPDATE_ENTITY_SERVICE,
        )

    @staticmethod
    def kasa() -> KasaPowerMeter:
        return KasaPowerMeter(config.KASA_DEVICE_IP)

    @staticmethod
    def manual() -> ManualPowerMeter:
        return ManualPowerMeter()

    @staticmethod
    def ocr() -> OcrPowerMeter:
        return OcrPowerMeter()

    @staticmethod
    def shelly() -> ShellyPowerMeter:
        return ShellyPowerMeter(config.SHELLY_IP, config.SHELLY_TIMEOUT)

    @staticmethod
    def tasmota() -> TasmotaPowerMeter:
        return TasmotaPowerMeter(config.TASMOTA_DEVICE_IP)

    @staticmethod
    def mystrom() -> MyStromPowerMeter:
        return MyStromPowerMeter(config.MYSTROM_DEVICE_IP)

    @staticmethod
    def tuya() -> TuyaPowerMeter:
        return TuyaPowerMeter(
            config.TUYA_DEVICE_ID,
            config.TUYA_DEVICE_IP,
            config.TUYA_DEVICE_KEY,
            config.TUYA_DEVICE_VERSION,
        )

    def create(self) -> PowerMeter:
        """Create the power meter object"""
        factories = {
            PowerMeterType.HASS: self.hass,
            PowerMeterType.KASA: self.kasa,
            PowerMeterType.MANUAL: self.manual,
            PowerMeterType.OCR: self.ocr,
            PowerMeterType.SHELLY: self.shelly,
            PowerMeterType.TASMOTA: self.tasmota,
            PowerMeterType.TUYA: self.tuya,
            PowerMeterType.DUMMY: self.dummy,
            PowerMeterType.MYSTROM: self.mystrom,
        }
        factory = factories.get(config.SELECTED_POWER_METER)
        if factory is None:
            raise PowerMeterError(
                f"Could not find a factory for {config.SELECTED_POWER_METER}",
            )

        return factory()
