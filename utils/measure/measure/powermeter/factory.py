import logging

from measure.config import MeasureConfig
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
    def __init__(self, config: MeasureConfig) -> None:
        self.config = config

    @staticmethod
    def dummy() -> DummyPowerMeter:
        return DummyPowerMeter()

    def hass(self) -> HassPowerMeter:
        return HassPowerMeter(
            self.config.hass_url,
            self.config.hass_token,
            self.config.hass_call_update_entity_service,
        )

    def kasa(self) -> KasaPowerMeter:
        return KasaPowerMeter(self.config.kasa_device_ip)

    @staticmethod
    def manual() -> ManualPowerMeter:
        return ManualPowerMeter()

    @staticmethod
    def ocr() -> OcrPowerMeter:
        return OcrPowerMeter()

    def shelly(self) -> ShellyPowerMeter:
        return ShellyPowerMeter(self.config.shelly_ip, self.config.shelly_timeout)

    def tasmota(self) -> TasmotaPowerMeter:
        return TasmotaPowerMeter(self.config.tasmota_device_ip)

    def mystrom(self) -> MyStromPowerMeter:
        return MyStromPowerMeter(self.config.mystrom_device_ip)

    def tuya(self) -> TuyaPowerMeter:
        return TuyaPowerMeter(
            self.config.tuya_device_id,
            self.config.tuya_device_ip,
            self.config.tuya_device_key,
            self.config.tuya_device_version,
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
        factory = factories.get(self.config.selected_power_meter)
        if factory is None:
            raise PowerMeterError(
                f"Could not find a factory for {self.config.selected_power_meter}",
            )

        return factory()
