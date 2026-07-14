from __future__ import annotations

from typing import Any

from measure.cli.environment import CliEnvironment
from measure.const import (
    QUESTION_ENTITY_ID,
    QUESTION_GENERATE_MODEL_JSON,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODEL_ID,
    QUESTION_MODEL_NAME,
    MeasureType,
)
from measure.controller.charging.const import (
    QUESTION_BATTERY_LEVEL_ATTRIBUTE,
    QUESTION_BATTERY_LEVEL_ENTITY,
    QUESTION_BATTERY_LEVEL_SOURCE_TYPE,
    BatteryLevelSourceType,
    ChargingControllerType,
    ChargingDeviceType,
)
from measure.controller.charging.spec import DummyChargingControllerSpec, HassChargingControllerSpec
from measure.controller.fan.const import FanControllerType
from measure.controller.fan.spec import DummyFanControllerSpec, HassFanControllerSpec
from measure.controller.light.const import LightControllerType
from measure.controller.light.spec import DummyLightControllerSpec, HassLightControllerSpec, HueLightControllerSpec
from measure.controller.media.const import MediaControllerType
from measure.controller.media.spec import DummyMediaControllerSpec, HassMediaControllerSpec
from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID, QUESTION_VOLTAGEMETER_ENTITY_ID, PowerMeterType
from measure.powermeter.spec import (
    DummyPowerMeterSpec,
    HassPowerMeterSpec,
    KasaPowerMeterSpec,
    ManualPowerMeterSpec,
    MyStromPowerMeterSpec,
    OcrPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
    TasmotaPowerMeterSpec,
    TuyaPowerMeterSpec,
)
from measure.request import (
    AverageMeasurementRequest,
    ChargingMeasurementRequest,
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    RecorderMeasurementRequest,
    ResumePolicy,
    SpeakerMeasurementRequest,
    validate_export_filename,
)
from measure.runner.const import (
    QUESTION_CHARGING_DEVICE_TYPE,
    QUESTION_DISABLE_STREAMING,
    QUESTION_DURATION,
    QUESTION_EXPORT_FILENAME,
    QUESTION_GZIP,
    QUESTION_MODE,
    QUESTION_NUM_LIGHTS,
)
from measure.tuning import MeasurementParameters


def request_from_answers(
    measure_type: MeasureType,
    answers: dict[str, Any],
    environment: CliEnvironment,
) -> MeasurementRequest:
    """Adapt CLI/Inquirer answers once at the transport boundary."""
    common: dict[str, Any] = {
        "model_id": str(answers.get(QUESTION_MODEL_ID, "measurement")),
        "product_name": str(answers.get(QUESTION_MODEL_NAME, "Measurement")),
        "measure_device": str(answers.get(QUESTION_MEASURE_DEVICE, "")),
        "generate_model": bool(answers.get(QUESTION_GENERATE_MODEL_JSON, False)),
        "power_meter": _power_meter_spec(environment, answers),
        "parameters": _parameters_from_environment(environment),
        "resume_policy": ResumePolicy.RESUME if environment.resume else ResumePolicy.NEW,
    }
    if measure_type == MeasureType.LIGHT:
        return LightMeasurementRequest(
            **common,
            controller=_light_controller_spec(environment, answers),
            modes=set(answers[QUESTION_MODE]),
            gzip=bool(answers.get(QUESTION_GZIP, True)),
            multiple_light_count=int(answers.get(QUESTION_NUM_LIGHTS) or 1),
        )
    if measure_type == MeasureType.AVERAGE:
        return AverageMeasurementRequest(
            **common,
            duration=int(answers[QUESTION_DURATION]),
        )
    if measure_type == MeasureType.RECORDER:
        return RecorderMeasurementRequest(
            **common,
            export_filename=validate_export_filename(str(answers[QUESTION_EXPORT_FILENAME])),
        )
    if measure_type == MeasureType.SPEAKER:
        return SpeakerMeasurementRequest(
            **common,
            controller=_media_controller_spec(environment, answers),
            disable_streaming=bool(answers.get(QUESTION_DISABLE_STREAMING, False)),
        )
    if measure_type == MeasureType.CHARGING:
        return ChargingMeasurementRequest(
            **common,
            controller=_charging_controller_spec(environment, answers),
            charging_device_type=ChargingDeviceType(answers[QUESTION_CHARGING_DEVICE_TYPE]),
        )
    return FanMeasurementRequest(
        **common,
        controller=_fan_controller_spec(environment, answers),
    )


def _parameters_from_environment(environment: CliEnvironment) -> MeasurementParameters:
    return MeasurementParameters(
        min_brightness=environment.min_brightness,
        max_brightness=environment.max_brightness,
        min_sat=environment.min_sat,
        max_sat=environment.max_sat,
        min_hue=environment.min_hue,
        max_hue=environment.max_hue,
        ct_bri_steps=environment.ct_bri_steps,
        ct_mired_steps=environment.ct_mired_steps,
        bri_bri_steps=environment.bri_bri_steps,
        hs_bri_steps=environment.hs_bri_steps,
        hs_hue_steps=environment.hs_hue_steps,
        hs_sat_steps=environment.hs_sat_steps,
        effect_bri_steps=environment.effect_bri_steps,
        measure_time_effect=environment.measure_time_effect,
        measure_time_effect_min=environment.measure_time_effect_min,
        measure_time_effect_convergence_window=environment.measure_time_effect_convergence_window,
        measure_time_effect_convergence_abs=environment.measure_time_effect_convergence_abs,
        measure_time_effect_convergence_rel=environment.measure_time_effect_convergence_rel,
        sleep_initial=environment.sleep_initial,
        sleep_standby=environment.sleep_standby,
        sleep_time=environment.sleep_time,
        sleep_time_sample=environment.sleep_time_sample,
        sleep_time_hue=environment.sleep_time_hue,
        sleep_time_sat=environment.sleep_time_sat,
        sleep_time_ct=environment.sleep_time_ct,
        sleep_time_effect_change=environment.sleep_time_effect_change,
        sleep_time_nudge=environment.sleep_time_nudge,
        pulse_time_nudge=environment.pulse_time_nudge,
        sample_count=environment.sample_count,
        max_retries=environment.max_retries,
        max_nudges=environment.max_nudges,
        prompt_resume=environment.prompt_resume,
        csv_add_datetime_column=environment.csv_add_datetime_column,
    )


def _power_meter_spec(environment: CliEnvironment, answers: dict[str, Any]) -> PowerMeterSpec:
    selected = environment.selected_power_meter
    if selected == PowerMeterType.DUMMY:
        return DummyPowerMeterSpec()
    if selected == PowerMeterType.HASS:
        return HassPowerMeterSpec(
            entity_id=_required_answer(answers, QUESTION_POWERMETER_ENTITY_ID),
            voltage_entity_id=_optional_answer(answers, QUESTION_VOLTAGEMETER_ENTITY_ID),
            call_update_entity=environment.hass_call_update_entity_service,
        )
    if selected == PowerMeterType.KASA:
        return KasaPowerMeterSpec(device_ip=environment.kasa_device_ip)
    if selected == PowerMeterType.MANUAL:
        return ManualPowerMeterSpec()
    if selected == PowerMeterType.MYSTROM:
        return MyStromPowerMeterSpec(device_ip=environment.mystrom_device_ip)
    if selected == PowerMeterType.OCR:
        return OcrPowerMeterSpec()
    if selected == PowerMeterType.SHELLY:
        return ShellyPowerMeterSpec(device_ip=environment.shelly_ip, timeout=environment.shelly_timeout)
    if selected == PowerMeterType.TASMOTA:
        return TasmotaPowerMeterSpec(device_ip=environment.tasmota_device_ip)
    if selected == PowerMeterType.TUYA:
        return TuyaPowerMeterSpec(
            device_id=environment.tuya_device_id,
            device_ip=environment.tuya_device_ip,
            version=environment.tuya_device_version,
        )
    raise ValueError(f"Unsupported CLI power meter: {selected}")


def _light_controller_spec(
    environment: CliEnvironment,
    answers: dict[str, Any],
) -> DummyLightControllerSpec | HassLightControllerSpec | HueLightControllerSpec:
    selected = environment.selected_light_controller
    if selected == LightControllerType.DUMMY:
        return DummyLightControllerSpec()
    if selected == LightControllerType.HASS:
        return HassLightControllerSpec(
            entity_id=_required_answer(answers, QUESTION_ENTITY_ID),
            transition_time=environment.light_transition_time,
        )
    if selected == LightControllerType.HUE:
        return HueLightControllerSpec(
            bridge_ip=environment.hue_bridge_ip,
            light=_required_answer(answers, "light"),
        )
    raise ValueError(f"Unsupported CLI light controller: {selected}")


def _media_controller_spec(
    environment: CliEnvironment,
    answers: dict[str, Any],
) -> DummyMediaControllerSpec | HassMediaControllerSpec:
    selected = environment.selected_media_controller
    if selected == MediaControllerType.DUMMY:
        return DummyMediaControllerSpec()
    if selected == MediaControllerType.HASS:
        return HassMediaControllerSpec(entity_id=_required_answer(answers, QUESTION_ENTITY_ID))
    raise ValueError(f"Unsupported CLI media controller: {selected}")


def _charging_controller_spec(
    environment: CliEnvironment,
    answers: dict[str, Any],
) -> DummyChargingControllerSpec | HassChargingControllerSpec:
    selected = environment.selected_charging_controller
    if selected == ChargingControllerType.DUMMY:
        return DummyChargingControllerSpec()
    if selected == ChargingControllerType.HASS:
        return HassChargingControllerSpec(
            entity_id=_required_answer(answers, QUESTION_ENTITY_ID),
            battery_level_source_type=BatteryLevelSourceType(
                answers.get(QUESTION_BATTERY_LEVEL_SOURCE_TYPE, BatteryLevelSourceType.ATTRIBUTE),
            ),
            battery_level_attribute=_optional_answer(answers, QUESTION_BATTERY_LEVEL_ATTRIBUTE),
            battery_level_entity_id=_optional_answer(answers, QUESTION_BATTERY_LEVEL_ENTITY),
        )
    raise ValueError(f"Unsupported CLI charging controller: {selected}")


def _fan_controller_spec(
    environment: CliEnvironment,
    answers: dict[str, Any],
) -> DummyFanControllerSpec | HassFanControllerSpec:
    selected = environment.selected_fan_controller
    if selected == FanControllerType.DUMMY:
        return DummyFanControllerSpec()
    if selected == FanControllerType.HASS:
        return HassFanControllerSpec(entity_id=_required_answer(answers, QUESTION_ENTITY_ID))
    raise ValueError(f"Unsupported CLI fan controller: {selected}")


def _required_answer(answers: dict[str, Any], key: str) -> str:
    value = _optional_answer(answers, key)
    if value is None:
        raise ValueError(f"Missing required CLI answer: {key}")
    return value


def _optional_answer(answers: dict[str, Any], key: str) -> str | None:
    value = answers.get(key)
    return str(value) if value not in {None, ""} else None
