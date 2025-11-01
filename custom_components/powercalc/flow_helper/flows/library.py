from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector, translation
import voluptuous as vol

from custom_components.powercalc import (
    DOMAIN,
    DeviceType,
)
from custom_components.powercalc.const import (
    CONF_AVAILABILITY_ENTITY,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_SELF_USAGE_INCLUDED,
    CONF_SUB_PROFILE,
    CONF_VARIABLES,
    LIBRARY_URL,
    CalculationStrategy,
)
from custom_components.powercalc.discovery import get_power_profile_by_source_entity
from custom_components.powercalc.flow_helper.common import FlowType, PowercalcFormStep, Step
from custom_components.powercalc.flow_helper.dynamic_field_builder import build_dynamic_field_schema
from custom_components.powercalc.flow_helper.schema import SCHEMA_ENERGY_SENSOR_TOGGLE, SCHEMA_UTILITY_METER_TOGGLE, build_sub_profile_schema
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary
from custom_components.powercalc.power_profile.power_profile import DEVICE_TYPE_DOMAIN, DOMAIN_DEVICE_TYPE_MAPPING, DiscoveryBy

if TYPE_CHECKING:
    from custom_components.powercalc.config_flow import PowercalcCommonFlow, PowercalcConfigFlow, PowercalcOptionsFlow

CONF_CONFIRM_AUTODISCOVERED_MODEL = "confirm_autodisovered_model"

SCHEMA_POWER_AUTODISCOVERED = vol.Schema(
    {vol.Optional(CONF_CONFIRM_AUTODISCOVERED_MODEL, default=True): bool},
)

SCHEMA_POWER_OPTIONS_LIBRARY = vol.Schema(
    {
        **SCHEMA_ENERGY_SENSOR_TOGGLE.schema,
        **SCHEMA_UTILITY_METER_TOGGLE.schema,
    },
)

SCHEMA_POWER_SMART_SWITCH = vol.Schema(
    {
        vol.Optional(CONF_POWER): vol.Coerce(float),
        vol.Optional(CONF_SELF_USAGE_INCLUDED): selector.BooleanSelector(),
    },
)


class LibraryFlow:
    def __init__(self, flow: PowercalcCommonFlow) -> None:
        self.flow = flow

    async def async_step_manufacturer(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Ask the user to select the manufacturer."""

        async def _create_schema() -> vol.Schema:
            """Create manufacturer schema."""
            library = await ProfileLibrary.factory(self.flow.hass)
            device_types = DOMAIN_DEVICE_TYPE_MAPPING.get(self.flow.source_entity.domain, set()) if self.flow.source_entity else None
            manufacturers = [
                selector.SelectOptionDict(value=manufacturer[0], label=manufacturer[1])
                for manufacturer in await library.get_manufacturer_listing(device_types)
            ]
            return vol.Schema(
                {
                    vol.Required(CONF_MANUFACTURER, default=self.flow.sensor_config.get(CONF_MANUFACTURER)): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=manufacturers,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                },
            )

        # noinspection PyTypeChecker
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.MANUFACTURER,
                schema=_create_schema,
                next_step=Step.MODEL,
            ),
            user_input,
        )

    async def async_step_model(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Ask the user to select the model."""

        async def _validate(user_input: dict[str, Any]) -> dict[str, str]:
            library = await ProfileLibrary.factory(self.flow.hass)
            profile = await library.get_profile(
                ModelInfo(
                    str(self.flow.sensor_config.get(CONF_MANUFACTURER)),
                    str(user_input.get(CONF_MODEL)),
                ),
                self.flow.source_entity,
            )
            self.flow.selected_profile = profile
            if self.flow.selected_profile and not await self.flow.selected_profile.needs_user_configuration:
                await self.flow.validate_strategy_config()
            return user_input

        async def _create_schema() -> vol.Schema:
            """Create model schema."""
            manufacturer = str(self.flow.sensor_config.get(CONF_MANUFACTURER))
            library = await ProfileLibrary.factory(self.flow.hass)
            device_types = DOMAIN_DEVICE_TYPE_MAPPING.get(self.flow.source_entity.domain, set()) if self.flow.source_entity else None
            models = [selector.SelectOptionDict(value=model, label=model) for model in await library.get_model_listing(manufacturer, device_types)]
            model = self.flow.selected_profile.model if self.flow.selected_profile else self.flow.sensor_config.get(CONF_MODEL)
            return vol.Schema(
                {
                    vol.Required(CONF_MODEL, description={"suggested_value": model}, default=model): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=models,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                },
            )

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.MODEL,
                schema=_create_schema,
                next_step=Step.POST_LIBRARY,
                validate_user_input=_validate,
                form_kwarg={"description_placeholders": {"supported_models_link": LIBRARY_URL}},
            ),
            user_input,
        )

    async def async_step_post_library(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """
        Handles the logic after the user either selected manufacturer/model himself or confirmed autodiscovered.
        Forwards to the next step in the flow.
        """
        if not self.flow.selected_profile:
            return self.flow.async_abort(reason="model_not_supported")  # type:ignore # pragma: no cover

        if Step.LIBRARY_CUSTOM_FIELDS not in self.flow.handled_steps and self.flow.selected_profile.has_custom_fields:
            return await self.async_step_library_custom_fields()

        if Step.AVAILABILITY_ENTITY not in self.flow.handled_steps and self.flow.selected_profile.discovery_by == DiscoveryBy.DEVICE:
            result = await self.async_step_availability_entity()
            if result:
                return result

        if Step.SUB_PROFILE not in self.flow.handled_steps and await self.flow.selected_profile.requires_manual_sub_profile_selection:
            return await self.async_step_sub_profile()

        if (
            Step.SMART_SWITCH not in self.flow.handled_steps
            and self.flow.selected_profile.device_type == DeviceType.SMART_SWITCH
            and self.flow.selected_profile.calculation_strategy == CalculationStrategy.FIXED
        ):
            return await self.async_step_smart_switch()

        if Step.FIXED not in self.flow.handled_steps and self.flow.selected_profile.needs_fixed_config:  # pragma: no cover
            return await self.flow.flow_handlers[FlowType.VIRTUAL_POWER].async_step_fixed()  # type:ignore

        if Step.LINEAR not in self.flow.handled_steps and self.flow.selected_profile.needs_linear_config:
            return await self.flow.flow_handlers[FlowType.VIRTUAL_POWER].async_step_linear()  # type:ignore

        if Step.MULTI_SWITCH not in self.flow.handled_steps and self.flow.selected_profile.calculation_strategy == CalculationStrategy.MULTI_SWITCH:
            return await self.flow.flow_handlers[FlowType.VIRTUAL_POWER].async_step_multi_switch()  # type:ignore

        return await self.flow.flow_handlers[FlowType.GROUP].async_step_assign_groups()  # type:ignore

    async def async_step_library_custom_fields(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the flow for custom fields."""

        async def _process_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
            return {CONF_VARIABLES: user_input}

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.LIBRARY_CUSTOM_FIELDS,
                schema=build_dynamic_field_schema(self.flow.selected_profile),  # type: ignore
                next_step=Step.POST_LIBRARY,
                validate_user_input=_process_user_input,
            ),
            user_input,
        )

    async def async_step_sub_profile(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the flow for sub profile selection."""

        async def _validate(user_input: dict[str, Any]) -> dict[str, str]:
            return {CONF_MODEL: f"{self.flow.sensor_config.get(CONF_MODEL)}/{user_input.get(CONF_SUB_PROFILE)}"}

        library = await ProfileLibrary.factory(self.flow.hass)
        profile = await library.get_profile(
            ModelInfo(
                str(self.flow.sensor_config.get(CONF_MANUFACTURER)),
                str(self.flow.sensor_config.get(CONF_MODEL)),
            ),
            self.flow.source_entity,
            process_variables=False,
        )
        remarks = profile.config_flow_sub_profile_remarks
        if remarks:
            remarks = "\n\n" + remarks

        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.SUB_PROFILE,
                schema=await build_sub_profile_schema(profile, self.flow.selected_sub_profile),
                next_step=Step.POWER_ADVANCED,
                validate_user_input=_validate,
                form_kwarg={
                    "description_placeholders": {
                        "entity_id": self.flow.source_entity_id,
                        "remarks": remarks,
                    },
                },
            ),
            user_input,
        )

    async def async_step_smart_switch(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Asks the user for the power of connect appliance for the smart switch."""

        if self.flow.selected_profile and not self.flow.selected_profile.needs_fixed_config:
            return self.flow.persist_config_entry()

        async def _validate(user_input: dict[str, Any]) -> dict[str, Any]:
            return {
                CONF_SELF_USAGE_INCLUDED: user_input.get(CONF_SELF_USAGE_INCLUDED),
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: user_input.get(CONF_POWER, 0)},
            }

        self_usage_on = self.flow.selected_profile.standby_power_on if self.flow.selected_profile else 0
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.SMART_SWITCH,
                schema=SCHEMA_POWER_SMART_SWITCH,
                validate_user_input=_validate,
                next_step=Step.POWER_ADVANCED,
                form_kwarg={"description_placeholders": {"self_usage_power": str(self_usage_on)}},
            ),
            user_input,
        )

    async def async_step_availability_entity(self, user_input: dict[str, Any] | None = None) -> FlowResult | None:
        """Handle the flow for availability entity."""
        domains = DEVICE_TYPE_DOMAIN[self.flow.selected_profile.device_type]  # type: ignore
        entity_selector = self.flow.create_device_entity_selector(
            list(domains) if isinstance(domains, set) else [domains],
        )
        try:
            first_entity = entity_selector.config["include_entities"][0]
        except IndexError:
            # Skip step if no entities are available
            self.flow.handled_steps.append(Step.AVAILABILITY_ENTITY)
            return None
        return await self.flow.handle_form_step(
            PowercalcFormStep(
                step=Step.AVAILABILITY_ENTITY,
                schema=vol.Schema(
                    {
                        vol.Optional(CONF_AVAILABILITY_ENTITY, default=first_entity): entity_selector,
                    },
                ),
                next_step=Step.POST_LIBRARY,
            ),
            user_input,
        )


class LibraryConfigFlow(LibraryFlow):
    def __init__(self, flow: PowercalcConfigFlow) -> None:
        super().__init__(flow)
        self.flow: PowercalcConfigFlow = flow

    async def async_step_library_multi_profile(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult | ConfigFlowResult:
        """This step gets executed when multiple profiles are found for the source entity."""
        if user_input is not None:
            selected_model: str = user_input.get(CONF_MODEL)  # type: ignore
            selected_profile = self.flow.discovered_profiles.get(selected_model)
            if selected_profile is None:  # pragma: no cover
                return self.flow.async_abort(reason="invalid_profile")
            self.flow.selected_profile = selected_profile
            self.flow.sensor_config.update(
                {
                    CONF_MANUFACTURER: selected_profile.manufacturer,
                    CONF_MODEL: selected_profile.model,
                },
            )
            return await self.async_step_post_library(user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_MODEL): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=profile.unique_id,
                                label=profile.model,
                            )
                            for profile in self.flow.discovered_profiles.values()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            },
        )

        manufacturer = str(self.flow.sensor_config.get(CONF_MANUFACTURER))
        model = str(self.flow.sensor_config.get(CONF_MODEL))
        return self.flow.async_show_form(
            step_id=Step.LIBRARY_MULTI_PROFILE,
            data_schema=schema,
            description_placeholders={
                "library_link": f"{LIBRARY_URL}/?manufacturer={manufacturer}",
                "manufacturer": manufacturer,
                "model": model,
            },
            last_step=False,
        )

    async def async_step_library(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Try to autodiscover manufacturer/model first.
        Ask the user to confirm this or forward to manual library selection.
        """
        if user_input is not None:
            if user_input.get(CONF_CONFIRM_AUTODISCOVERED_MODEL) and self.flow.selected_profile:
                self.flow.sensor_config.update(
                    {
                        CONF_MANUFACTURER: self.flow.selected_profile.manufacturer,
                        CONF_MODEL: self.flow.selected_profile.model,
                    },
                )
                return await self.async_step_post_library(user_input)

            return await self.async_step_manufacturer()

        if self.flow.source_entity and self.flow.source_entity.entity_entry and self.flow.selected_profile is None:
            self.flow.selected_profile = await get_power_profile_by_source_entity(self.flow.hass, self.flow.source_entity)
        if self.flow.selected_profile:
            remarks = self.flow.selected_profile.config_flow_discovery_remarks
            if remarks:
                remarks = "\n\n" + remarks

            translations = translation.async_get_cached_translations(self.flow.hass, self.flow.hass.config.language, "common", DOMAIN)
            if self.flow.selected_profile.discovery_by == DiscoveryBy.DEVICE and self.flow.source_entity and self.flow.source_entity.device_entry:
                source = f"{translations.get(f'component.{DOMAIN}.common.source_device')}: {self.flow.source_entity.device_entry.name}"
            else:
                source = f"{translations.get(f'component.{DOMAIN}.common.source_entity')}: {self.flow.source_entity_id}"

            return self.flow.async_show_form(
                step_id=Step.LIBRARY,
                description_placeholders={
                    "remarks": remarks,  # type: ignore
                    "manufacturer": self.flow.selected_profile.manufacturer,
                    "model": self.flow.selected_profile.model,
                    "source": source,
                },
                data_schema=SCHEMA_POWER_AUTODISCOVERED,
                errors={},
                last_step=False,
            )

        return await self.async_step_manufacturer()


class LibraryOptionsFlow(LibraryFlow):
    def __init__(self, flow: PowercalcOptionsFlow) -> None:
        super().__init__(flow)
        self.flow: PowercalcOptionsFlow = flow

    async def async_step_library_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the basic options flow."""
        self.flow.is_library_flow = True
        self.flow.selected_sub_profile = self.flow.selected_profile.sub_profile  # type: ignore
        if user_input is not None:
            return await self.async_step_manufacturer()

        return self.flow.async_show_form(
            step_id=Step.LIBRARY_OPTIONS,
            description_placeholders={
                "manufacturer": self.flow.selected_profile.manufacturer,  # type: ignore
                "model": self.flow.selected_profile.model,  # type: ignore
            },
            last_step=False,
        )
