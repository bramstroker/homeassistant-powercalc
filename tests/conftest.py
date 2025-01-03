import asyncio
import json
import os
import shutil
import uuid
from collections.abc import Generator
from typing import Any, Protocol
from unittest.mock import AsyncMock, patch

import pytest
from _pytest.fixtures import SubRequest
from homeassistant import loader
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntry
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from custom_components.powercalc.helpers import get_library_json_path, get_library_path
from tests.common import mock_area_registry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: bool) -> Generator:
    yield


@pytest.fixture(autouse=True)
def enable_event_loop_debug(event_loop: asyncio.AbstractEventLoop) -> None:
    """Override the fixture to disable event loop debug mode."""
    event_loop.set_debug(False)  # Modify this behavior as needed


@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    """Temporary ability to bypass test failures.
    Parametrize to True to bypass the pytest failure.
    @pytest.mark.parametrize("expected_lingering_timers", [True])
    This should be removed when all lingering timers have been cleaned up.
    See https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/issues/153
    """
    return True


@pytest.fixture
def enable_custom_integrations(hass: HomeAssistant) -> None:
    """Enable custom integrations defined in the test dir."""
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS)


@pytest.fixture
def area_reg(hass: HomeAssistant) -> AreaRegistry:
    """Return an empty, loaded, registry."""
    return mock_area_registry(hass)


@pytest.fixture
def device_reg(hass: HomeAssistant) -> DeviceRegistry:
    """Return an empty, loaded, registry."""
    return mock_device_registry(hass)


@pytest.fixture
def entity_reg(hass: HomeAssistant) -> EntityRegistry:
    """Return an empty, loaded, registry."""
    return mock_registry(hass)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "input_boolean.test",
            CONF_FIXED: {
                CONF_POWER: 50,
            },
        },
        unique_id="aabbccddeeff",
        title="test",
    )


@pytest.fixture
def mock_flow_init(hass: HomeAssistant) -> Generator:
    """Mock hass.config_entries.flow.async_init."""
    with patch.object(
        hass.config_entries.flow,
        "async_init",
        return_value=AsyncMock(),
    ) as mock_init:
        yield mock_init


class MockEntityWithModel(Protocol):
    def __call__(
        self,
        entity_id: str,
        manufacturer: str = "signify",
        model: str = "LCT010",
        model_id: str | None = None,
        **entity_reg_kwargs: Any,  # noqa: ANN401
    ) -> None: ...


@pytest.fixture
def mock_entity_with_model_information(hass: HomeAssistant) -> MockEntityWithModel:
    def _mock_entity_with_model_information(
        entity_id: str,
        manufacturer: str = "signify",
        model: str = "LCT010",
        model_id: str | None = None,
        **entity_reg_kwargs: Any,  # noqa: ANN401
    ) -> None:
        device_id = str(uuid.uuid4())
        if "device_id" in entity_reg_kwargs:
            device_id = entity_reg_kwargs["device_id"]
            del entity_reg_kwargs["device_id"]

        unique_id = str(uuid.uuid4())
        if "unique_id" in entity_reg_kwargs:
            unique_id = entity_reg_kwargs["unique_id"]
            del entity_reg_kwargs["unique_id"]

        platform = "foo"
        if "platform" in entity_reg_kwargs:
            platform = entity_reg_kwargs["platform"]
            del entity_reg_kwargs["platform"]

        mock_registry(
            hass,
            {
                entity_id: RegistryEntry(
                    entity_id=entity_id,
                    unique_id=unique_id,
                    platform=platform,
                    device_id=device_id,
                    **entity_reg_kwargs,
                ),
            },
        )
        mock_device_registry(
            hass,
            {
                device_id: DeviceEntry(
                    id=device_id,
                    manufacturer=manufacturer,
                    model=model,
                    model_id=model_id,
                ),
            },
        )

    return _mock_entity_with_model_information


@pytest.fixture(autouse=True)
def mock_remote_loader(request: SubRequest, hass: HomeAssistant) -> Generator:
    if "skip_remote_loader_mocking" in request.keywords:
        yield
        return

    def side_effect(manufacturer: str, model: str, storage_path: str) -> None:
        source_dir = get_library_path(f"{manufacturer}/{model}")
        if os.path.exists(storage_path):
            return
        shutil.copytree(source_dir, storage_path)

    remote_loader_class = "custom_components.powercalc.power_profile.loader.remote.RemoteLoader"
    with patch(f"{remote_loader_class}.download_profile") as mock_download, patch(f"{remote_loader_class}.load_library_json") as mock_load_lib:
        mock_download.side_effect = side_effect

        def load_library_json() -> dict:
            with open(get_library_json_path()) as f:
                return json.load(f)

        mock_load_lib.side_effect = load_library_json
        yield
