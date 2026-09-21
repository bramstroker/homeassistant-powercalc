from dataclasses import dataclass, replace

from fastapi import HTTPException

from measure.controller.light.const import LutMode
from measure.dummy_load import power_meter_fingerprint
from measure.ha_app.context import AppContext
from measure.ha_app.coordinator import SessionConflictError
from measure.ha_app.light_probe import LightLoadProbeResult
from measure.ha_app.preflight import ActiveSessionError, MeasurementPreflight, PreflightError, PreflightResult
from measure.ha_app.session import is_active_session
from measure.home_assistant.entities import DeviceClass, EntityDescriptor, EntityDomain, HomeAssistantEntityCatalog
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import DummyLoadReuseRequest, LightMeasurementRequest, MeasurementRequest


@dataclass(frozen=True)
class PreflightAssessment:
    checks: PreflightResult
    light_load_probe: LightLoadProbeResult | None = None


def run_preflight(context: AppContext, payload: MeasurementRequest, *, refresh: bool = False) -> PreflightAssessment:
    """Validate app dependencies and probe low light loads before starting a run."""
    try:
        with context.coordinator.reserve_devices():
            return _run_preflight(context, payload, refresh=refresh)
    except SessionConflictError as error:
        raise ActiveSessionError(str(error)) from error


def _run_preflight(context: AppContext, payload: MeasurementRequest, *, refresh: bool) -> PreflightAssessment:
    if isinstance(payload.dummy_load, DummyLoadReuseRequest):
        calibration = context.storage.load_dummy_load_calibration()
        if (
            calibration is None
            or calibration.power_meter_fingerprint != power_meter_fingerprint(payload.power_meter)
            or calibration.description != payload.dummy_load.description
            or calibration.resistance != payload.dummy_load.resistance
        ):
            raise PreflightError("No compatible saved dummy-load calibration is available. Calibrate this setup first.")
    catalog = HomeAssistantEntityCatalog(context.home_assistant)
    snapshot = None

    def load_entities(domain: EntityDomain | None, device_class: DeviceClass | None) -> list[EntityDescriptor]:
        nonlocal snapshot
        if snapshot is None:
            snapshot = catalog.load_snapshot()
        return snapshot.select(domain=domain, device_class=device_class)

    result = MeasurementPreflight(
        has_active_session=lambda: is_active_session(context.coordinator.current),
        verify_storage=context.storage.verify_writable,
        load_entities=load_entities,
        load_all_entities=lambda: catalog.load_snapshot().get_all(),
        diagnose_power_meter=context.power_meter_diagnostics.evaluate,
        developer_mode=context.developer_mode,
    ).validate(payload)
    light_load_probe = (
        _evaluate_light_load_probe(context, payload, refresh=refresh)
        if isinstance(payload, LightMeasurementRequest)
        and payload.dummy_load is None
        and not payload.controller.is_dummy
        and not isinstance(payload.power_meter, DummyPowerMeterSpec)
        and bool(payload.modes - {LutMode.EFFECT})
        else None
    )
    return PreflightAssessment(result, light_load_probe)


def _evaluate_light_load_probe(
    context: AppContext,
    payload: LightMeasurementRequest,
    *,
    refresh: bool,
) -> LightLoadProbeResult:
    if refresh:
        return context.light_load_probe.evaluate(payload, refresh=True)
    return context.light_load_probe.evaluate(payload)


def apply_fast_test_mode(context: AppContext, request: MeasurementRequest) -> MeasurementRequest:
    settings = context.storage.load_settings()
    controller = request.controller
    supported_dummy_controller = controller is not None and controller.is_dummy
    enabled = (
        context.developer_mode
        and settings.fast_test_mode
        and isinstance(request.power_meter, DummyPowerMeterSpec)
        and supported_dummy_controller
    )
    parameters = replace(request.parameters, fast_test_mode=False)
    if enabled:
        parameters = replace(
            request.parameters,
            fast_test_mode=True,
            sleep_time=0,
            sleep_time_sample=0,
            sample_count=1,
            sleep_initial=0,
            sleep_standby=0,
            sleep_time_hue=0,
            sleep_time_sat=0,
            sleep_time_ct=0,
            sleep_time_effect_change=0,
            measure_time_effect=1,
            measure_time_effect_min=1,
        )
    return request.model_copy(update={"fast_test_mode": enabled, "parameters": parameters})


def validate_standby_setup(context: AppContext, payload: MeasurementRequest) -> None:
    catalog = HomeAssistantEntityCatalog(context.home_assistant)
    try:
        MeasurementPreflight(
            has_active_session=lambda: False,
            verify_storage=lambda: None,
            developer_mode=context.developer_mode,
            load_entities=lambda domain, device_class: catalog.load_snapshot().select(
                domain=domain, device_class=device_class
            ),
        ).validate_standby(payload)
    except PreflightError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
