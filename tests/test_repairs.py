import attr
from homeassistant.components.repairs import RepairsFlowManager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import CONF_SENSOR_TYPE, DOMAIN, SensorType
from custom_components.powercalc.const import (
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_POWER,
    ISSUE_COMPOSITE_DEVICE_ID,
)
from custom_components.powercalc.repairs import async_create_fix_flow
from tests.common import create_mock_config_entry

COMPOSITE_ID = "composite00000000000000000000ab"


async def test_sub_profile_repair(hass: HomeAssistant, issue_registry: ir.IssueRegistry) -> None:
    """Test sub profile repair"""
    config_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile",
        },
    )

    issue = issue_registry.async_get_issue("powercalc", f"sub_profile_{config_entry.entry_id}")
    assert issue

    # Dispatch repair flow and see if we can change the sub_profile
    # After the repair, the config entry should have the new sub_profile set in the data
    assert await async_setup_component(hass, "repairs", {})
    flow_manager = RepairsFlowManager(hass)
    result = await flow_manager.async_init(DOMAIN, data={"issue_id": issue.issue_id})
    assert result["type"] == "form"
    assert result["step_id"] == "sub_profile"

    result = await flow_manager.async_configure(result["flow_id"], user_input={"sub_profile": "a"})
    assert result["type"] == "create_entry"

    assert config_entry.data[CONF_MODEL] == "sub_profile/a"


async def test_no_sub_profile_repair_raised(hass: HomeAssistant, issue_registry: ir.IssueRegistry) -> None:
    config_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile_matchers",
        },
    )

    issue = issue_registry.async_get_issue("powercalc", f"sub_profile_{config_entry.entry_id}")
    assert not issue


@pytest.mark.parametrize(
    ("issue_data", "error"),
    [
        (None, "Missing config entry ID for repair flow"),
        ({"config_entry_id": "missing"}, "Unknown config entry: missing"),
    ],
)
async def test_invalid_repair_flow_data(
    hass: HomeAssistant,
    issue_data: dict[str, str] | None,
    error: str,
) -> None:
    """Invalid repair metadata raises a descriptive error."""
    with pytest.raises(ValueError, match=error):
        await async_create_fix_flow(hass, "sub_profile_missing", issue_data)


@pytest.fixture
def split_devices(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> tuple[dr.DeviceEntry, dr.DeviceEntry]:
    """Create two devices split from the same pre-migration composite device."""
    entry_1 = MockConfigEntry(domain="test_1")
    entry_1.add_to_hass(hass)
    entry_2 = MockConfigEntry(domain="test_2")
    entry_2.add_to_hass(hass)
    device_1 = device_registry.async_get_or_create(
        config_entry_id=entry_1.entry_id,
        identifiers={("test_1", "1")},
        name="Split device 1",
    )
    device_2 = device_registry.async_get_or_create(
        config_entry_id=entry_2.entry_id,
        identifiers={("test_2", "1")},
        name="Split device 2",
    )
    device_registry.devices[device_1.id] = attr.evolve(device_1, composite_device_id=COMPOSITE_ID)
    device_registry.devices[device_2.id] = attr.evolve(device_2, composite_device_id=COMPOSITE_ID)
    return device_registry.devices[device_1.id], device_registry.devices[device_2.id]


@pytest.mark.skip(reason="Enable when Home Assistant 2026.8 is released")
@pytest.mark.usefixtures("split_devices")
async def test_composite_device_creates_repair_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """A stored composite device ID creates a repair and leaves entities unlinked."""
    config_entry = await _setup_powercalc_entry(hass, COMPOSITE_ID)

    issue = issue_registry.async_get_issue(DOMAIN, _composite_issue_id(config_entry))
    assert issue
    assert issue.data == {"config_entry_id": config_entry.entry_id}
    assert issue.translation_placeholders == {"name": "Legacy helper"}

    entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert entities
    assert all(entity.device_id is None for entity in entities)


@pytest.mark.skip(reason="Enable when Home Assistant 2026.8 is released")
async def test_live_device_creates_no_repair_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    split_devices: tuple[dr.DeviceEntry, dr.DeviceEntry],
) -> None:
    """A concrete split device does not create a repair."""
    config_entry = await _setup_powercalc_entry(hass, split_devices[0].id)

    assert issue_registry.async_get_issue(DOMAIN, _composite_issue_id(config_entry)) is None


@pytest.mark.skip(reason="Enable when Home Assistant 2026.8 is released")
@pytest.mark.usefixtures("split_devices")
async def test_no_device_creates_no_repair_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A config entry without a selected device does not create a repair."""
    config_entry = await _setup_powercalc_entry(hass, None)

    assert issue_registry.async_get_issue(DOMAIN, _composite_issue_id(config_entry)) is None


@pytest.mark.skip(reason="Enable when Home Assistant 2026.8 is released")
@pytest.mark.parametrize("pick_device", [True, False], ids=["pick_device", "unlink"])
async def test_composite_device_repair_updates_device(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    entity_registry: er.EntityRegistry,
    split_devices: tuple[dr.DeviceEntry, dr.DeviceEntry],
    pick_device: bool,
) -> None:
    """The repair can select a concrete split device or leave entities unlinked."""
    config_entry = await _setup_powercalc_entry(hass, COMPOSITE_ID)
    selected_device_id = split_devices[0].id if pick_device else None
    flow_manager, result = await _start_composite_repair(hass, config_entry)

    user_input = {CONF_DEVICE: selected_device_id} if selected_device_id else {}
    result = await flow_manager.async_configure(result["flow_id"], user_input=user_input)
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert config_entry.data.get(CONF_DEVICE) == selected_device_id
    assert issue_registry.async_get_issue(DOMAIN, _composite_issue_id(config_entry)) is None
    entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert entities
    assert all(entity.device_id == selected_device_id for entity in entities)


@pytest.mark.skip(reason="Enable when Home Assistant 2026.8 is released")
@pytest.mark.parametrize("selected_device_id", [COMPOSITE_ID, "unknown-device"])
@pytest.mark.usefixtures("split_devices")
async def test_composite_device_repair_rejects_invalid_device(
    hass: HomeAssistant,
    selected_device_id: str,
) -> None:
    """The repair remains open for a composite or unknown device ID."""
    config_entry = await _setup_powercalc_entry(hass, COMPOSITE_ID)
    flow_manager, result = await _start_composite_repair(hass, config_entry)

    result = await flow_manager.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE: selected_device_id},
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_device"}
    assert config_entry.data[CONF_DEVICE] == COMPOSITE_ID


@pytest.mark.skip(reason="Enable when Home Assistant 2026.8 is released")
@pytest.mark.usefixtures("split_devices")
async def test_composite_device_repair_aborts_when_entry_removed(
    hass: HomeAssistant,
) -> None:
    """An open repair handles its config entry being removed."""
    config_entry = await _setup_powercalc_entry(hass, COMPOSITE_ID)
    flow_manager, result = await _start_composite_repair(hass, config_entry)
    assert await hass.config_entries.async_remove(config_entry.entry_id)

    result = await flow_manager.async_configure(result["flow_id"], user_input={})

    assert result["type"] == "abort"
    assert result["reason"] == "entry_removed"


async def _setup_powercalc_entry(hass: HomeAssistant, device_id: str | None) -> ConfigEntry:
    """Set up a fixed Powercalc sensor linked to a device when provided."""
    hass.states.async_set("light.composite_test", "on")
    data = {
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_ENTITY_ID: "light.composite_test",
        CONF_FIXED: {CONF_POWER: 1},
    }
    if device_id is not None:
        data[CONF_DEVICE] = device_id
    return await create_mock_config_entry(hass, data, title="Legacy helper")


def _composite_issue_id(config_entry: ConfigEntry) -> str:
    return f"{ISSUE_COMPOSITE_DEVICE_ID}_{config_entry.entry_id}"


async def _start_composite_repair(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> tuple[RepairsFlowManager, dict]:
    assert await async_setup_component(hass, "repairs", {})
    flow_manager = RepairsFlowManager(hass)
    result = await flow_manager.async_init(DOMAIN, data={"issue_id": _composite_issue_id(config_entry)})
    assert result["type"] == "form"
    assert result["step_id"] == "select_device"
    return flow_manager, result
