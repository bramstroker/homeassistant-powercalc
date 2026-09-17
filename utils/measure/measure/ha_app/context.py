from collections.abc import Sequence
import logging
from pathlib import Path
from typing import cast

from fastapi import HTTPException, Request

from measure.assembler import MeasurementAssembler
from measure.ha_app.contribution.coordinator import ContributionApiCoordinator
from measure.ha_app.coordinator import MeasurementCoordinator
from measure.ha_app.library_catalog import (
    DeviceSpecificationCatalog,
    LibraryCatalogError,
    ManufacturerCatalog,
    MeasureDeviceCatalog,
)
from measure.ha_app.light_probe import LightLoadProbe, app_measurement_assembler
from measure.ha_app.service import MeasurementService
from measure.ha_app.session import SessionSnapshot
from measure.ha_app.storage import SESSION_LOAD_ERRORS, SessionStorage
from measure.home_assistant.client import HomeAssistantManager
from measure.home_assistant.entities import EntityDescriptor, HomeAssistantEntityCatalog
from measure.powermeter.diagnostics import PowerMeterDiagnostics
from measure.powermeter.powermeter import PowerMeter
from measure.powermeter.spec import PowerMeterSpec
from measure.runner.interaction import ImmediateInteraction

_LOGGER = logging.getLogger("measure")


class AppContext:
    def __init__(
        self,
        *,
        data_root: Path,
        hass_url: str,
        hass_token: str,
        trusted_ingress_only: bool,
        developer_mode: bool = False,
    ) -> None:
        self.home_assistant = HomeAssistantManager(hass_url, hass_token)
        self.trusted_ingress_only = trusted_ingress_only
        self.developer_mode = developer_mode
        self.storage = SessionStorage(data_root)
        self.measure_device_catalog = MeasureDeviceCatalog()
        self.manufacturer_catalog = ManufacturerCatalog()
        self.device_specification_catalog = DeviceSpecificationCatalog()
        self.power_meter_diagnostics = PowerMeterDiagnostics(self.build_power_meter)
        self.light_load_probe = LightLoadProbe(
            lambda: app_measurement_assembler(
                home_assistant=self.home_assistant,
                shelly_password=self.shelly_password(),
                kasa_credentials=self.tapo_credentials(),
            ),
        )
        self.contribution = ContributionApiCoordinator(
            self.storage,
            resolve_integration=self.entity_integrations,
            resolve_manufacturer=self.entity_manufacturers,
            resolve_model_id=self.entity_model_ids,
        )
        self.coordinator = MeasurementCoordinator(
            self.storage,
            self._measurement_service,
        )

    def entity_integrations(self, entity_ids: Sequence[str]) -> dict[str, str | None]:
        """Look up which integration provides each entity; contribution details stay usable without it."""
        entities = self._entity_descriptors(entity_ids, "integration")
        return {entity_id: entity.integration if entity is not None else None for entity_id, entity in entities.items()}

    def entity_manufacturers(self, entity_ids: Sequence[str]) -> dict[str, str | None]:
        """Look up HA's device manufacturer per entity and normalize known aliases to the library name."""
        entities = self._entity_descriptors(entity_ids, "manufacturer")
        return {
            entity_id: self._canonical_manufacturer(entity.manufacturer) if entity is not None else None
            for entity_id, entity in entities.items()
        }

    def entity_model_ids(self, entity_ids: Sequence[str]) -> dict[str, str | None]:
        entities = self._entity_descriptors(entity_ids, "model ID")
        return {entity_id: entity.model_id if entity is not None else None for entity_id, entity in entities.items()}

    def _entity_descriptors(self, entity_ids: Sequence[str], purpose: str) -> dict[str, EntityDescriptor | None]:
        """Read one entity snapshot for the whole batch, rather than one per entity."""
        try:
            snapshot = HomeAssistantEntityCatalog(self.home_assistant).load_snapshot()
        except Exception as error:  # noqa: BLE001 - this metadata is optional context for a pull request
            _LOGGER.warning("Could not resolve the %s for %s: %s", purpose, ", ".join(entity_ids), error)
            return dict.fromkeys(entity_ids)
        return {entity_id: snapshot.get(entity_id) for entity_id in entity_ids}

    def _canonical_manufacturer(self, manufacturer: str | None) -> str | None:
        if not manufacturer:
            return None
        try:
            return self.manufacturer_catalog.canonical_name(manufacturer)
        except LibraryCatalogError as error:
            _LOGGER.warning("Could not normalize manufacturer %s: %s", manufacturer, error)
            return manufacturer

    def _measurement_service(self) -> MeasurementService:
        return MeasurementService(
            self.home_assistant,
            self.storage,
            shelly_password=self.shelly_password(),
            kasa_credentials=self.tapo_credentials(),
        )

    def shelly_password(self) -> str | None:
        credentials = self.storage.load_shelly_credentials()
        return credentials.password if credentials is not None else None

    def tapo_credentials(self) -> tuple[str, str] | None:
        credentials = self.storage.load_tapo_credentials()
        return (credentials.username, credentials.password) if credentials is not None else None

    def build_power_meter(self, spec: PowerMeterSpec) -> PowerMeter:
        return MeasurementAssembler(
            ImmediateInteraction(),
            home_assistant=self.home_assistant,
            shelly_password=self.shelly_password(),
            kasa_credentials=self.tapo_credentials(),
        ).build_power_meter(spec)


def app_context(request: Request) -> AppContext:
    return cast(AppContext, request.app.state.context)


def require_session(context: AppContext, session_id: str) -> SessionSnapshot:
    try:
        return context.coordinator.get(session_id)
    except SESSION_LOAD_ERRORS as error:
        raise HTTPException(status_code=404, detail="Measurement session not found") from error
