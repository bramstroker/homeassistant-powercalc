from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from measure.powermeter.const import PowerMeterType

POWER_ENTITY_PATTERN = r"^sensor\.[a-z0-9_]+$"
VOLTAGE_ENTITY_PATTERN = r"^sensor\.[a-z0-9_]+$"


class _PowerMeterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DummyPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.DUMMY] = PowerMeterType.DUMMY


class HassPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.HASS] = PowerMeterType.HASS
    entity_id: str = Field(pattern=POWER_ENTITY_PATTERN)
    voltage_entity_id: str | None = Field(default=None, pattern=VOLTAGE_ENTITY_PATTERN)
    call_update_entity: bool = False

    @field_validator("voltage_entity_id", mode="before")
    @classmethod
    def empty_voltage_entity_is_none(cls, value: str | None) -> str | None:
        return value or None


class KasaPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.KASA] = PowerMeterType.KASA
    device_ip: str


class ManualPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.MANUAL] = PowerMeterType.MANUAL


class MyStromPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.MYSTROM] = PowerMeterType.MYSTROM
    device_ip: str


class OcrPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.OCR] = PowerMeterType.OCR


class ShellyPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.SHELLY] = PowerMeterType.SHELLY
    device_ip: str
    timeout: int = 5


class TasmotaPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.TASMOTA] = PowerMeterType.TASMOTA
    device_ip: str


class TuyaPowerMeterSpec(_PowerMeterSpec):
    type: Literal[PowerMeterType.TUYA] = PowerMeterType.TUYA
    device_id: str
    device_ip: str
    version: str = "3.3"


PowerMeterSpec = Annotated[
    DummyPowerMeterSpec
    | HassPowerMeterSpec
    | KasaPowerMeterSpec
    | ManualPowerMeterSpec
    | MyStromPowerMeterSpec
    | OcrPowerMeterSpec
    | ShellyPowerMeterSpec
    | TasmotaPowerMeterSpec
    | TuyaPowerMeterSpec,
    Field(discriminator="type"),
]
