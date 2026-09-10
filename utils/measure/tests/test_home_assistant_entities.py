from types import SimpleNamespace
from unittest.mock import MagicMock

from measure.controller.light.const import LutMode
from measure.home_assistant import HomeAssistantEntityData, HomeAssistantManager
from measure.home_assistant_entities import DeviceClass, EntityDomain, HomeAssistantEntityCatalog
import pytest


def _entity(entity_id: str, state: str, **attributes: object) -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=entity_id,
        state=SimpleNamespace(state=state, attributes=attributes),
    )


def _entity_data(*, power_state: str = "4.2") -> HomeAssistantEntityData:
    return HomeAssistantEntityData(
        entities={
            "light": SimpleNamespace(
                entities={
                    "desk": _entity(
                        "light.desk",
                        "on",
                        friendly_name="Desk light",
                        supported_color_modes=["brightness", "color_temp", "hs"],
                        effect_list=["colorloop"],
                        min_color_temp_kelvin=2202,
                        max_color_temp_kelvin=6535,
                    ),
                    "switch": _entity(
                        "light.switch_like",
                        "on",
                        friendly_name="Switch-like light",
                        supported_color_modes=["onoff"],
                    ),
                },
            ),
            "vacuum": SimpleNamespace(
                entities={
                    "robot": _entity(
                        "vacuum.robot",
                        "docked",
                        friendly_name="Robot",
                        battery_level=80,
                        status="docked",
                    ),
                },
            ),
            "sensor": SimpleNamespace(
                entities={
                    "power": _entity(
                        "sensor.desk_power",
                        power_state,
                        friendly_name="Desk power",
                        device_class="power",
                        unit_of_measurement="W",
                    ),
                    "voltage": _entity(
                        "sensor.desk_voltage",
                        "230",
                        friendly_name="Desk voltage",
                        device_class="voltage",
                        unit_of_measurement="V",
                    ),
                    "unknown": _entity(
                        "sensor.unknown_power",
                        "unknown",
                        device_class="power",
                        unit_of_measurement="W",
                    ),
                    "text": _entity(
                        "sensor.text_power",
                        "not-a-number",
                        device_class="power",
                        unit_of_measurement="W",
                    ),
                },
            ),
        },
        entity_registry=[
            SimpleNamespace(entity_id="light.desk", device_id="light-device", platform="hue"),
            SimpleNamespace(entity_id="sensor.desk_power", device_id="meter-device", platform="shelly"),
            SimpleNamespace(entity_id="sensor.desk_voltage", device_id="meter-device", platform="shelly"),
        ],
        device_registry=[
            {
                "id": "light-device",
                "manufacturer": "Signify",
                "model_id": "LWA017",
                "model": "Hue White Ambiance",
            },
            {"id": "meter-device", "model_id": "PM-001", "model": "Power Meter"},
        ],
    )


def test_catalog_applies_one_selection_policy_and_enriches_entities() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = _entity_data()

    snapshot = HomeAssistantEntityCatalog(home_assistant).load_snapshot()

    lights = snapshot.select(domain=EntityDomain.LIGHT)
    assert [entity.entity_id for entity in lights] == ["light.desk"]
    assert lights[0].model_id == "LWA017"
    assert lights[0].product_name == "Hue White Ambiance"
    assert lights[0].manufacturer == "Signify"
    assert lights[0].integration == "hue"
    assert lights[0].supported_modes == [LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT]
    assert lights[0].min_mired == 153
    assert lights[0].max_mired == 454

    powers = snapshot.select(device_class=DeviceClass.POWER)
    assert [entity.entity_id for entity in powers] == ["sensor.desk_power"]
    assert powers[0].related_voltage_entity_id == "sensor.desk_voltage"
    assert powers[0].model_id == "PM-001"

    assert snapshot.attribute_names("vacuum.robot") == ["battery_level", "friendly_name", "status"]
    home_assistant.get_entity_data.assert_called_once_with()


def test_catalog_loads_entity_data_once_per_instance() -> None:
    """Interactive choices call load_snapshot on every keypress; it must not hit Home Assistant each time."""
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.side_effect = (
        _entity_data(power_state="1.0"),
        _entity_data(power_state="2.0"),
    )

    catalog = HomeAssistantEntityCatalog(home_assistant)
    first = catalog.load_snapshot().select(device_class=DeviceClass.POWER)
    second = catalog.load_snapshot().select(device_class=DeviceClass.POWER)

    assert first[0].state == "1.0"
    assert second[0].state == "1.0"
    assert home_assistant.get_entity_data.call_count == 1

    fresh = HomeAssistantEntityCatalog(home_assistant).load_snapshot().select(device_class=DeviceClass.POWER)
    assert fresh[0].state == "2.0"


def test_catalog_all_includes_arbitrary_domains_and_unavailable_entities() -> None:
    data = _entity_data()
    data.entities["climate"] = SimpleNamespace(
        entities={"room": _entity("climate.room", "unavailable", friendly_name="Room thermostat")},
    )
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = data

    entities = HomeAssistantEntityCatalog(home_assistant).load_snapshot().all()
    thermostat = next(entity for entity in entities if entity.entity_id == "climate.room")

    assert thermostat.domain == "climate"
    assert thermostat.state == "unavailable"


def test_catalog_omits_attribute_detail_for_unmeasurable_domains() -> None:
    """Every Home Assistant entity reaches the "any entity" pickers, so the rows stay small."""

    data = _entity_data()
    data.entities["climate"] = SimpleNamespace(
        entities={
            "room": _entity(
                "climate.room",
                "heat",
                friendly_name="Room thermostat",
                temperature=21,
                hvac_modes=["heat", "cool"],
            ),
        },
    )
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = data

    entities = HomeAssistantEntityCatalog(home_assistant).load_snapshot().all()
    thermostat = next(entity for entity in entities if entity.entity_id == "climate.room")
    light = next(entity for entity in entities if entity.domain == "light")

    assert thermostat.name == "Room thermostat"
    assert thermostat.state == "heat"
    assert thermostat.attribute_names == []
    # A measurable domain still carries the detail preflight and the selectors read.
    assert light.attribute_names


def test_catalog_handles_light_with_null_effect_list() -> None:
    data = _entity_data()
    data.entities["light"].entities["desk"].state.attributes["effect_list"] = None
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = data

    lights = HomeAssistantEntityCatalog(home_assistant).load_snapshot().select(domain=EntityDomain.LIGHT)

    assert lights[0].effect_list is None


def test_catalog_exposes_group_members_and_infers_their_shared_model() -> None:
    data = _entity_data()
    data.entities["light"].entities["second"] = _entity(
        "light.second",
        "on",
        supported_color_modes=["brightness"],
    )
    group = _entity(
        "light.group",
        "on",
        supported_color_modes=["brightness"],
    )
    group.state.attributes["entity_id"] = ["light.desk", "light.second"]
    data.entities["light"].entities["group"] = group
    data.entity_registry.append(SimpleNamespace(entity_id="light.second", device_id="light-device", platform="hue"))
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = data

    lights = HomeAssistantEntityCatalog(home_assistant).load_snapshot().select(domain=EntityDomain.LIGHT)
    group = next(light for light in lights if light.entity_id == "light.group")

    assert group.member_entity_ids == ["light.desk", "light.second"]
    assert group.model_id == "LWA017"
    assert group.product_name == "Hue White Ambiance"
    assert group.manufacturer == "Signify"


def test_snapshot_requires_exactly_one_entity_filter() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_entity_data.return_value = _entity_data()
    snapshot = HomeAssistantEntityCatalog(home_assistant).load_snapshot()

    with pytest.raises(ValueError, match="Specify exactly one entity filter"):
        snapshot.select()

    with pytest.raises(ValueError, match="Specify exactly one entity filter"):
        snapshot.select(domain=EntityDomain.LIGHT, device_class=DeviceClass.POWER)
