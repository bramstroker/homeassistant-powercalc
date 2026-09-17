from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from measure.assembler import MeasurementAssembler
from measure.const import PARAMETER_LIMITS
from measure.controller.light.const import LutMode
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.ha_app.api_models import (
    ERROR_RESPONSE,
    CapabilitiesResponse,
    DeviceSpecificationCatalogResponse,
    DeviceSpecificationFieldResponse,
    EntityCatalogResponse,
    FormField,
    FormFieldOption,
    ManufacturerCatalogResponse,
    MeasureDefinition,
    MeasureDeviceCatalogResponse,
    MeasurementRequestPayload,
    MeasureParameter,
    PreflightResponse,
)
from measure.ha_app.context import AppContext, app_context
from measure.ha_app.errors import DocumentedHTTPException
from measure.ha_app.library_catalog import (
    LibraryCatalogError,
)
from measure.ha_app.light_probe import (
    LightLoadProbeError,
)
from measure.ha_app.preferences import AppPreferences, AppSettingsResponse, AppSettingsUpdate
from measure.ha_app.preflight import ActiveSessionError, MeasurementPreflight, PreflightError
from measure.ha_app.registry import measurement_definitions
from measure.ha_app.session import (
    is_active_session,
)
from measure.ha_app.shelly_credentials import ShellyCredentials
from measure.ha_app.shelly_discovery import ShellyDiscoveryResponse, ShellyDiscoveryService
from measure.ha_app.tapo_credentials import TapoCredentials
from measure.home_assistant.entities import (
    DeviceClass,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import PowerMeterType
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.spec import (
    DummyPowerMeterSpec,
    HassPowerMeterSpec,
    KasaPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
)
from measure.request import LightMeasurementRequest, MeasurementRequest
from measure.runner.interaction import ImmediateInteraction
from measure.tuning import MeasurementParameters
from measure.utils.version import measure_version

CACHE_CONTROL_LIBRARY = "public, max-age=600"


router = APIRouter()


@router.get("/capabilities")
async def capabilities(request: Request) -> CapabilitiesResponse:
    context = app_context(request)
    defaults = MeasurementParameters()
    settings = await run_in_threadpool(context.storage.load_settings)
    return CapabilitiesResponse(
        runtime_version=measure_version(),
        defaults={name: getattr(defaults, name) for name in PARAMETER_LIMITS}
        | settings.measurement_defaults.model_dump(),
        limits={name: {"min": minimum, "max": maximum} for name, (minimum, maximum) in PARAMETER_LIMITS.items()},
        developer_mode=context.developer_mode,
        fast_test_mode=context.developer_mode and settings.fast_test_mode,
    )


@router.get("/measure-definitions")
async def measure_definitions() -> list[MeasureDefinition]:
    return _measure_definitions()


@router.get("/library/measure-devices", responses={503: ERROR_RESPONSE})
async def measure_devices(request: Request, response: Response) -> MeasureDeviceCatalogResponse:
    try:
        devices = await run_in_threadpool(app_context(request).measure_device_catalog.devices)
    except LibraryCatalogError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response.headers["Cache-Control"] = CACHE_CONTROL_LIBRARY
    return MeasureDeviceCatalogResponse(devices=list(devices))


@router.get("/library/manufacturers", responses={503: ERROR_RESPONSE})
async def manufacturers(request: Request, response: Response) -> ManufacturerCatalogResponse:
    try:
        values = await run_in_threadpool(app_context(request).manufacturer_catalog.manufacturers)
    except LibraryCatalogError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response.headers["Cache-Control"] = CACHE_CONTROL_LIBRARY
    return ManufacturerCatalogResponse(manufacturers=list(values))


@router.get("/library/device-specifications", responses={503: ERROR_RESPONSE})
async def device_specifications(request: Request, response: Response) -> DeviceSpecificationCatalogResponse:
    try:
        values = await run_in_threadpool(app_context(request).device_specification_catalog.fields)
    except LibraryCatalogError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response.headers["Cache-Control"] = CACHE_CONTROL_LIBRARY
    return DeviceSpecificationCatalogResponse(
        device_types={
            device_type: [
                DeviceSpecificationFieldResponse(
                    name=field.name,
                    label=field.label,
                    description=field.description,
                    value_type=field.value_type,
                    collection=field.collection,
                    options=list(field.options),
                )
                for field in fields
            ]
            for device_type, fields in values.items()
        },
    )


@router.get("/settings")
async def get_settings(request: Request) -> AppSettingsResponse:
    return await run_in_threadpool(_settings_response, app_context(request))


@router.put("/settings", responses={400: ERROR_RESPONSE})
async def update_settings(payload: AppSettingsUpdate, request: Request) -> AppSettingsResponse:
    context = app_context(request)
    if payload.fast_test_mode and not context.developer_mode:
        raise HTTPException(status_code=400, detail="Fast test mode requires developer mode")
    return await run_in_threadpool(_save_settings, context, payload)


@router.post("/settings/test-power-meter")
async def test_power_meter(payload: AppSettingsUpdate, request: Request) -> PowerMeterDiagnostic:
    return await run_in_threadpool(_test_power_meter, app_context(request), payload)


@router.get("/power-meters/shelly")
async def discover_shelly_power_meters(request: Request) -> ShellyDiscoveryResponse:
    return await ShellyDiscoveryService(app_context(request).home_assistant).discover()


@router.get("/dummy-load/calibration")
async def dummy_load_calibration(request: Request) -> DummyLoadCalibration | None:
    return await run_in_threadpool(_matching_dummy_load_calibration, app_context(request))


@router.get("/entity-catalog")
async def entity_catalog(request: Request) -> EntityCatalogResponse:
    home_assistant = app_context(request).home_assistant
    config = await run_in_threadpool(home_assistant.get_config)
    if config.get("state") != "RUNNING":
        return EntityCatalogResponse(
            home_assistant_ready=False,
            lights=[],
            powers=[],
            voltages=[],
        )
    snapshot = await run_in_threadpool(
        HomeAssistantEntityCatalog(home_assistant).load_snapshot,
    )
    return EntityCatalogResponse(
        home_assistant_ready=True,
        lights=snapshot.select(domain=EntityDomain.LIGHT),
        powers=snapshot.select(device_class=DeviceClass.POWER),
        voltages=snapshot.select(device_class=DeviceClass.VOLTAGE),
    )


@router.get("/entities", responses={400: ERROR_RESPONSE})
async def entities(
    request: Request,
    domain: Annotated[EntityDomain | None, Query()] = None,
    device_class: Annotated[DeviceClass | None, Query()] = None,
    all_entities: Annotated[bool, Query(alias="all")] = False,
) -> list[EntityDescriptor]:
    if sum((domain is not None, device_class is not None, all_entities)) != 1:
        raise HTTPException(status_code=400, detail="Specify exactly one entity filter")
    snapshot = await run_in_threadpool(
        HomeAssistantEntityCatalog(app_context(request).home_assistant).load_snapshot,
    )
    return snapshot.all() if all_entities else snapshot.select(domain=domain, device_class=device_class)


@router.post("/preflight", responses={409: ERROR_RESPONSE, 422: ERROR_RESPONSE})
async def preflight(payload: MeasurementRequestPayload, request: Request) -> PreflightResponse:
    context = app_context(request)
    prepared = await run_in_threadpool(apply_fast_test_mode, context, payload)
    return await run_in_threadpool(run_preflight, context, prepared)


def _measure_definitions() -> list[MeasureDefinition]:
    return [
        MeasureDefinition(
            measure_type=definition.measure_type,
            label=definition.label,
            description=definition.description,
            icon=definition.icon,
            confirmation_action=definition.confirmation_action,
            confirmation_is_warning=definition.confirmation_is_warning,
            model_id_example=definition.model_id_example,
            product_name_example=definition.product_name_example,
            parameters=[MeasureParameter(**vars(parameter)) for parameter in definition.parameters],
            fields=[
                FormField(
                    name=field.name,
                    label=field.label,
                    control=field.control,
                    role=field.role,
                    narrowed_by=field.narrowed_by,
                    required=field.required,
                    entity_domains=list(field.entity_domains),
                    options=[
                        FormFieldOption(
                            value=option.value,
                            label=option.label,
                            entity_domain=option.entity_domain,
                            enables=list(option.enables),
                            description=option.description,
                            guidance=list(option.guidance),
                        )
                        for option in field.options
                    ],
                    default=field.default,
                    minimum=field.minimum,
                    maximum=field.maximum,
                    multiple=field.multiple,
                    plural_label=field.plural_label,
                    derived_from=field.derived_from,
                    hint=field.hint,
                    visible_when={name: list(values) for name, values in field.visible_when},
                    all_entities=field.all_entities,
                    entity_device_classes=list(field.entity_device_classes),
                    related_to=field.related_to,
                    same_device_only=field.same_device_only,
                    review=field.review,
                )
                for field in definition.fields
            ],
            supports_profile=definition.supports_profile,
            supports_resume=definition.supports_resume,
        )
        for definition in measurement_definitions()
    ]


def _settings_response(context: AppContext) -> AppSettingsResponse:
    settings = context.storage.load_settings()
    return AppSettingsResponse.model_validate(
        settings.model_dump()
        | {
            "shelly_password_configured": context.shelly_password() is not None,
            "tapo_credentials_configured": context.tapo_credentials() is not None,
        },
    )


def _save_settings(context: AppContext, update: AppSettingsUpdate) -> AppSettingsResponse:
    if update.clear_shelly_password:
        context.storage.clear_shelly_credentials()
    elif update.shelly_password:
        context.storage.save_shelly_credentials(ShellyCredentials(password=update.shelly_password))
    if update.clear_tapo_credentials:
        context.storage.clear_tapo_credentials()
    elif update.tapo_username and update.tapo_password:
        context.storage.save_tapo_credentials(
            TapoCredentials(username=update.tapo_username, password=update.tapo_password),
        )
    context.storage.save_settings(update.preferences())
    return _settings_response(context)


def _test_power_meter(context: AppContext, settings: AppSettingsUpdate) -> PowerMeterDiagnostic:
    """Validate connectivity and measurement quality for the configured meter."""
    try:
        spec = _power_meter_spec(settings.preferences())
    except PowerMeterError as error:
        message = str(error)
        return PowerMeterDiagnostic(
            success=False,
            status=DiagnosticStatus.POOR,
            precision_status=DiagnosticStatus.UNSUPPORTED,
            update_interval_status=DiagnosticStatus.UNSUPPORTED,
            messages=[message],
            message=message,
        )
    password = None if settings.clear_shelly_password else settings.shelly_password or context.shelly_password()
    tapo_credentials = None
    if not settings.clear_tapo_credentials:
        if settings.tapo_username and settings.tapo_password:
            tapo_credentials = (settings.tapo_username, settings.tapo_password)
        else:
            tapo_credentials = context.tapo_credentials()
    return context.power_meter_diagnostics.evaluate(
        spec,
        force=True,
        build_power_meter=lambda power_meter_spec: MeasurementAssembler(
            ImmediateInteraction(),
            home_assistant=context.home_assistant,
            shelly_password=password,
            kasa_credentials=tapo_credentials,
        ).build_power_meter(power_meter_spec),
    )


def _power_meter_spec(settings: AppPreferences) -> PowerMeterSpec:
    if settings.power_meter == PowerMeterType.DUMMY:
        return DummyPowerMeterSpec()
    if settings.power_meter == PowerMeterType.SHELLY:
        if not settings.shelly_ip:
            raise PowerMeterError("Enter the Shelly IP address first")
        return ShellyPowerMeterSpec(device_ip=settings.shelly_ip, username=settings.shelly_username)
    if settings.power_meter == PowerMeterType.KASA:
        if not settings.kasa_ip:
            raise PowerMeterError("Enter the Kasa IP address first")
        return KasaPowerMeterSpec(device_ip=settings.kasa_ip)
    if not settings.default_power_entity_id:
        raise PowerMeterError("Select a power sensor first")
    return HassPowerMeterSpec(entity_id=settings.default_power_entity_id)


def _matching_dummy_load_calibration(context: AppContext) -> DummyLoadCalibration | None:
    calibration = context.storage.load_dummy_load_calibration()
    if calibration is None:
        return None
    try:
        spec = _power_meter_spec(context.storage.load_settings())
    except PowerMeterError:
        return None
    if isinstance(spec, HassPowerMeterSpec):
        snapshot = HomeAssistantEntityCatalog(context.home_assistant).load_snapshot()
        spec = spec.model_copy(
            update={
                "voltage_entity_id": snapshot.related_entity_id(spec.entity_id, DeviceClass.VOLTAGE),
            },
        )
    return calibration if calibration.power_meter_fingerprint == power_meter_fingerprint(spec) else None


def run_preflight(context: AppContext, payload: MeasurementRequest) -> PreflightResponse:
    catalog = HomeAssistantEntityCatalog(context.home_assistant)
    snapshot = None

    def load_entities(
        domain: EntityDomain | None,
        device_class: DeviceClass | None,
    ) -> list[EntityDescriptor]:
        nonlocal snapshot
        if snapshot is None:
            snapshot = catalog.load_snapshot()
        return snapshot.select(domain=domain, device_class=device_class)

    try:
        result = MeasurementPreflight(
            has_active_session=lambda: is_active_session(context.coordinator.current),
            verify_storage=context.storage.verify_writable,
            load_entities=load_entities,
            load_all_entities=lambda: catalog.load_snapshot().all(),
            diagnose_power_meter=context.power_meter_diagnostics.evaluate,
            developer_mode=context.developer_mode,
        ).validate(payload)
        light_load_probe = (
            context.light_load_probe.evaluate(payload)
            if isinstance(payload, LightMeasurementRequest)
            and payload.dummy_load is None
            and not payload.controller.is_dummy
            and not isinstance(payload.power_meter, DummyPowerMeterSpec)
            and bool(payload.modes - {LutMode.EFFECT})
            else None
        )
    except ActiveSessionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except LightLoadProbeError as error:
        if error.help_url is None or error.help_label is None:
            raise HTTPException(status_code=422, detail=str(error)) from error
        raise DocumentedHTTPException(
            status_code=422,
            detail=str(error),
            help_url=error.help_url,
            help_label=error.help_label,
        ) from error
    except PreflightError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return PreflightResponse(
        valid=True,
        warnings=list(result.warnings),
        estimated_variations=result.estimated_variations,
        estimated_duration_seconds=result.estimated_duration_seconds,
        supported_modes=list(result.supported_modes) if result.supported_modes is not None else None,
        power_meter_diagnostic=result.power_meter_diagnostic,
        battery_level_entity_id=result.battery_level_entity_id,
        battery_level_attribute=result.battery_level_attribute,
        light_load_probe=light_load_probe,
    )


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
