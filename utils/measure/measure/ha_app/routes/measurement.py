from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from measure.assembler import MeasurementAssembler
from measure.const import PARAMETER_LIMITS
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
from measure.ha_app.context import AppContext, get_app_context
from measure.ha_app.library_catalog import (
    LibraryCatalogError,
)
from measure.ha_app.preferences import AppPreferences, AppSettingsResponse, AppSettingsUpdate
from measure.ha_app.preparation import apply_fast_test_mode, run_preflight
from measure.ha_app.registry import measurement_definitions
from measure.ha_app.shelly_credentials import ShellyCredentials
from measure.ha_app.shelly_discovery import ShellyDiscoveryResponse, ShellyDiscoveryService
from measure.home_assistant.entities import (
    DeviceClass,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import PowerMeterType
from measure.powermeter.credentials import TapoCredentials
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.spec import (
    DummyPowerMeterSpec,
    HassPowerMeterSpec,
    KasaPowerMeterSpec,
    PowerMeterSpec,
    ShellyPowerMeterSpec,
)
from measure.profile.standby import StandbyEstimate
from measure.runner.interaction import ImmediateInteraction
from measure.tuning import MeasurementParameters
from measure.utils.version import measure_version

CACHE_CONTROL_LIBRARY = "public, max-age=600"


router = APIRouter()


@router.get("/library/standby-estimate")
async def standby_estimate(
    request: Request,
    manufacturer: str = "",
    connectivity: Annotated[list[str] | None, Query()] = None,
) -> StandbyEstimate:
    return await run_in_threadpool(get_app_context(request).standby_catalog.estimate, manufacturer, connectivity or [])


@router.get("/capabilities")
async def capabilities(request: Request) -> CapabilitiesResponse:
    context = get_app_context(request)
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
        devices = await run_in_threadpool(get_app_context(request).measure_device_catalog.devices)
    except LibraryCatalogError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response.headers["Cache-Control"] = CACHE_CONTROL_LIBRARY
    return MeasureDeviceCatalogResponse(devices=devices)


@router.get("/library/manufacturers", responses={503: ERROR_RESPONSE})
async def manufacturers(request: Request, response: Response) -> ManufacturerCatalogResponse:
    try:
        values = await run_in_threadpool(get_app_context(request).manufacturer_catalog.manufacturers)
    except LibraryCatalogError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response.headers["Cache-Control"] = CACHE_CONTROL_LIBRARY
    return ManufacturerCatalogResponse(manufacturers=values)


@router.get("/library/device-specifications", responses={503: ERROR_RESPONSE})
async def device_specifications(request: Request, response: Response) -> DeviceSpecificationCatalogResponse:
    try:
        values = await run_in_threadpool(get_app_context(request).device_specification_catalog.fields)
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
    return await run_in_threadpool(_settings_response, get_app_context(request))


@router.put("/settings", responses={400: ERROR_RESPONSE})
async def update_settings(payload: AppSettingsUpdate, request: Request) -> AppSettingsResponse:
    context = get_app_context(request)
    if payload.fast_test_mode and not context.developer_mode:
        raise HTTPException(status_code=400, detail="Fast test mode requires developer mode")
    return await run_in_threadpool(_save_settings, context, payload)


@router.post("/settings/test-power-meter")
async def test_power_meter(payload: AppSettingsUpdate, request: Request) -> PowerMeterDiagnostic:
    return await run_in_threadpool(_test_power_meter, get_app_context(request), payload)


@router.get("/power-meters/shelly")
async def discover_shelly_power_meters(request: Request) -> ShellyDiscoveryResponse:
    return await ShellyDiscoveryService(get_app_context(request).home_assistant).discover()


@router.post("/dummy-load/calibration/match")
def matching_dummy_load_calibration(payload: PowerMeterSpec, request: Request) -> DummyLoadCalibration | None:
    calibration = get_app_context(request).storage.load_dummy_load_calibration()
    if calibration is not None and calibration.power_meter_fingerprint == power_meter_fingerprint(payload):
        return calibration
    return None


@router.get("/dummy-load/calibration")
async def dummy_load_calibration(request: Request) -> DummyLoadCalibration | None:
    return await run_in_threadpool(_matching_dummy_load_calibration, get_app_context(request))


@router.get("/entity-catalog")
async def entity_catalog(request: Request) -> EntityCatalogResponse:
    home_assistant = get_app_context(request).home_assistant
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
        HomeAssistantEntityCatalog(get_app_context(request).home_assistant).load_snapshot,
    )
    return snapshot.get_all() if all_entities else snapshot.select(domain=domain, device_class=device_class)


@router.post("/preflight", responses={409: ERROR_RESPONSE, 422: ERROR_RESPONSE})
async def preflight(payload: MeasurementRequestPayload, request: Request, refresh: bool = False) -> PreflightResponse:
    context = get_app_context(request)
    prepared = await run_in_threadpool(apply_fast_test_mode, context, payload)
    assessment = await run_in_threadpool(run_preflight, context, prepared, refresh=refresh)
    result = assessment.checks
    return PreflightResponse(
        valid=True,
        warnings=result.warnings,
        estimated_variations=result.estimated_variations,
        estimated_duration_seconds=result.estimated_duration_seconds,
        supported_modes=result.supported_modes,
        power_meter_diagnostic=result.power_meter_diagnostic,
        battery_level_entity_id=result.battery_level_entity_id,
        battery_level_attribute=result.battery_level_attribute,
        light_load_probe=assessment.light_load_probe,
    )


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
            "shelly_password_configured": context.get_shelly_password() is not None,
            "tapo_credentials_configured": context.get_tapo_credentials() is not None,
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
    password = None if settings.clear_shelly_password else settings.shelly_password or context.get_shelly_password()
    tapo_credentials = None
    if not settings.clear_tapo_credentials:
        if settings.tapo_username and settings.tapo_password:
            tapo_credentials = TapoCredentials(username=settings.tapo_username, password=settings.tapo_password)
        else:
            tapo_credentials = context.get_tapo_credentials()
    return context.power_meter_diagnostics.evaluate(
        spec,
        force=True,
        create_power_meter=lambda power_meter_spec: MeasurementAssembler(
            ImmediateInteraction(),
            home_assistant=context.home_assistant,
            shelly_password=password,
            kasa_credentials=tapo_credentials,
        ).create_power_meter(power_meter_spec),
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
                "voltage_entity_id": snapshot.find_related_entity_id(spec.entity_id, DeviceClass.VOLTAGE),
            },
        )
    return calibration if calibration.power_meter_fingerprint == power_meter_fingerprint(spec) else None
