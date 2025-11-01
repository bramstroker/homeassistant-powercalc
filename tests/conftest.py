from collections.abc import Callable, Generator
from datetime import timedelta
import json
import os
import shutil
from typing import Any, Protocol
from unittest.mock import AsyncMock, patch
import uuid

from _pytest.fixtures import SubRequest
from homeassistant import loader
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import Throttle
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    RegistryEntryWithDefaults,
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
                entity_id: RegistryEntryWithDefaults(
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


def _collect_throttles(func: Callable) -> Generator[Throttle]:
    """Yield any captured Throttle objects across wraps."""
    seen = set()
    while func is not None:
        closure = getattr(func, "__closure__", ()) or ()
        for cell in closure:
            obj = getattr(cell, "cell_contents", None)
            if obj is not None and id(obj) not in seen and obj.__class__.__name__ == "Throttle":
                seen.add(id(obj))
                yield obj
        func = getattr(func, "__wrapped__", None)


def _defang_throttle(thrs: list[Throttle]) -> None:
    for t in thrs:
        t.min_time = timedelta(0)
        t.limit_no_throttle = None


def _restore_throttle(originals: list[tuple[Throttle, timedelta, timedelta | None]]) -> None:
    for t, min_time, limit_nt in originals:
        t.min_time = min_time
        t.limit_no_throttle = limit_nt


_ORIGINAL_THROTTLES = []


@pytest.fixture(autouse=True, scope="session")
def _disable_power_throttle_by_default() -> None:
    from custom_components.powercalc.sensors.group.custom import GroupedSensor
    from custom_components.powercalc.sensors.power import VirtualPowerSensor

    # Disable throttling for VirtualPowerSensor
    target1 = VirtualPowerSensor._handle_source_entity_state_change_throttled  # noqa: SLF001
    throttles1 = list(_collect_throttles(target1))

    # Disable throttling for GroupedSensor
    target2 = GroupedSensor.on_state_change_throttled
    throttles2 = list(_collect_throttles(target2))

    throttles = throttles1 + throttles2
    if not throttles:
        return

    _ORIGINAL_THROTTLES[:] = [(t, t.min_time, t.limit_no_throttle) for t in throttles]

    _defang_throttle(throttles)


@pytest.fixture
def enable_throttle() -> Generator[None]:
    """Use real throttling in this test, then turn it off again."""
    _restore_throttle(_ORIGINAL_THROTTLES)
    try:
        yield
    finally:
        _defang_throttle([t for t, *_ in _ORIGINAL_THROTTLES])
