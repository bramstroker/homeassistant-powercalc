"""Replay generated measurement profiles through PowerCalc's real HA strategies."""

from importlib import import_module
import json
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from jsonschema import validate
import pytest

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.helpers import collect_placeholders, replace_placeholders
from custom_components.powercalc.power_profile.library import ProfileLibrary
from custom_components.powercalc.strategy.composite import CONFIG_SCHEMA
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from tests.common import mock_devices, mock_entities_in_registry


@pytest.mark.parametrize("registry_metadata", [True, False])
async def test_generated_vacuum_profile_matches_runtime(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, registry_metadata: bool
) -> None:
    # The utility is a separate project, but the analyser itself is offline and
    # needs no HA API client. Import locally to keep integration imports clean.
    root = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(root / "utils" / "measure"))
    models = import_module("measure.analyser.models")
    vacuum = import_module("measure.analyser.vacuum")
    primary, battery, status = "vacuum.robot", "sensor.battery", "sensor.activity"
    entities = (
        models.RecordedEntity(primary, "vacuum", "primary", device_id="robot"),
        models.RecordedEntity(battery, "sensor", "battery", device_id="robot", device_class="battery", unit="%"),
        models.RecordedEntity(status, "sensor", "tracked", device_id="robot", translation_key="state"),
    )
    if not registry_metadata:
        entities = tuple(models.RecordedEntity(entity.entity_id, entity.domain, entity.role) for entity in entities)
    context = models.AnalysisContext("vacuum_robot", primary, "vacuum_robot", entities)
    samples = _runtime_samples(models)
    candidate = vacuum.VacuumCompositeStrategy().build_candidate(samples, context)
    assert isinstance(candidate, vacuum.VacuumCompositeCandidate)
    fragment = candidate.build_model_config_fragment().to_dict()
    with (root / "profile_library" / "model_schema.json").open() as schema:
        validate(
            {
                "name": "Test vacuum",
                "device_type": "vacuum_robot",
                "measure_method": "manual",
                "measure_device": "Test meter",
                "created_at": "2026-09-16T00:00:00Z",
                **fragment,
            },
            json.load(schema),
        )

    mock_devices(hass, {"robot": {"manufacturer": "Test", "model": "Robot"}})
    mock_entities_in_registry(
        hass,
        {
            primary: {"device_id": "robot", "platform": "test"},
            battery: {"device_id": "robot", "platform": "test", "device_class": "battery"},
            status: {"device_id": "robot", "platform": "test", "translation_key": "state"},
        },
    )
    source = create_source_entity(primary, hass)
    library = ProfileLibrary(hass, MagicMock())
    replacements = library.compute_replacement_variables(collect_placeholders(fragment), {}, source)
    resolved = replace_placeholders(fragment, replacements)
    strategy = await PowerCalculatorStrategyFactory(hass).create(
        {"composite": CONFIG_SCHEMA(resolved["composite_config"])}, "composite", None, source
    )

    for sample in samples:
        for entity_id, state in sample.entities.items():
            hass.states.async_set(entity_id, state.state, state.attributes)
        result = await strategy.calculate(hass.states.get(primary))
        assert result is not None
        assert float(result) == pytest.approx(candidate.estimate_power(sample), abs=0.001)

    # Guard malformed and out-of-range batteries rather than extrapolating or
    # throwing from LinearStrategy. Decimal strings are valid sensor states only.
    charging = samples[-1]
    for value in ("unknown", "unavailable", "bad", -1, 19, 81, 101, "NaN", "inf", "45.9", True):
        states = dict(charging.entities)
        states[primary] = models.RecordedEntityState("docked", {**states[primary].attributes, "battery_level": value})
        states[battery] = models.RecordedEntityState(str(value), {})
        sample = models.RecordingSample(0, 0, states)
        for entity_id, state in sample.entities.items():
            hass.states.async_set(entity_id, state.state, state.attributes)
        result = await strategy.calculate(hass.states.get(primary))
        estimate = candidate.estimate_power(sample)
        if estimate is None:
            assert result is None
        else:
            assert float(result) == pytest.approx(estimate, abs=0.001)

    # Boolean flags must not accidentally match an unseen numeric enum of 1.
    sleeping = samples[0]
    states = dict(sleeping.entities)
    states[primary] = models.RecordedEntityState("docked", {**states[primary].attributes, "washing": 1})
    sample = models.RecordingSample(0, 0, states)
    for entity_id, state in sample.entities.items():
        hass.states.async_set(entity_id, state.state, state.attributes)
    assert candidate.estimate_power(sample) is None
    assert await strategy.calculate(hass.states.get(primary)) is None


@pytest.mark.parametrize("integration", ["dreame_vacuum", "roborock", "ecovacs"])
async def test_integration_signals_match_exported_profile(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    integration: str,
) -> None:
    root = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(root / "utils" / "measure"))
    models = import_module("measure.analyser.models")
    vacuum = import_module("measure.analyser.vacuum")
    primary, battery = "vacuum.robot", "sensor.battery"
    descriptions = [
        models.RecordedEntity(primary, "vacuum", "primary", device_id="robot"),
        models.RecordedEntity(battery, "sensor", "battery", device_id="robot", device_class="battery", unit="%"),
    ]
    keys = {
        "dreame_vacuum": ["state", "self_wash_base_status", "auto_empty_status"],
        "roborock": ["status"],
        "ecovacs": ["station_state"],
    }[integration]
    descriptions.extend(
        models.RecordedEntity(
            "sensor." + key, "sensor", "tracked", device_id="robot", translation_key=key, integration=integration
        )
        for key in keys
    )
    if integration == "ecovacs":
        descriptions.append(
            models.RecordedEntity(
                "binary_sensor.charge",
                "binary_sensor",
                "tracked",
                device_id="robot",
                device_class="battery_charging",
                integration=integration,
            )
        )
    context = models.AnalysisContext("vacuum_robot", primary, "vacuum_robot", tuple(descriptions))
    samples = []
    for item in _runtime_samples(models):
        activity = item.entities[primary].attributes["vacuum_state"]
        states = {
            primary: models.RecordedEntityState("cleaning" if activity == "cleaning" else "docked", {}),
            battery: item.entities[battery],
        }
        if integration == "dreame_vacuum":
            states.update(
                {
                    "sensor.state": models.RecordedEntityState(
                        "charging_completed" if activity == "sleeping" else activity, {}
                    ),
                    "sensor.self_wash_base_status": models.RecordedEntityState(
                        activity if activity in {"washing", "drying"} else "idle", {}
                    ),
                    "sensor.auto_empty_status": models.RecordedEntityState(
                        "active" if activity == "auto_emptying" else "not_performed", {}
                    ),
                }
            )
        elif integration == "roborock":
            label = {
                "sleeping": "charging_complete",
                "washing": "washing_the_mop",
                "auto_emptying": "emptying_the_bin",
                "cleaning": "segment_cleaning",
            }.get(activity, activity)
            states["sensor.status"] = models.RecordedEntityState(label, {})
        else:
            label = {"washing": "washing_mop", "drying": "drying_mop", "auto_emptying": "emptying_dustbin"}.get(
                activity, "idle"
            )
            states["sensor.station_state"] = models.RecordedEntityState(label, {})
            states["binary_sensor.charge"] = models.RecordedEntityState("on" if activity == "charging" else "off", {})
        samples.append(models.RecordingSample(item.elapsed_seconds, item.power, states))
    candidate = vacuum.VacuumCompositeStrategy().build_candidate(samples, context)
    assert isinstance(candidate, vacuum.VacuumCompositeCandidate)
    fragment = candidate.build_model_config_fragment().to_dict()
    mock_devices(hass, {"robot": {"manufacturer": "Test", "model": "Robot"}})
    mock_entities_in_registry(
        hass,
        {
            entity.entity_id: {
                "device_id": "robot",
                "platform": integration,
                "translation_key": entity.translation_key,
                "device_class": entity.device_class,
            }
            for entity in descriptions
        },
    )
    source = create_source_entity(primary, hass)
    replacements = ProfileLibrary(hass, MagicMock()).compute_replacement_variables(
        collect_placeholders(fragment), {}, source
    )
    resolved = replace_placeholders(fragment, replacements)
    strategy = await PowerCalculatorStrategyFactory(hass).create(
        {"composite": CONFIG_SCHEMA(resolved["composite_config"])},
        "composite",
        None,
        source,
    )
    for item in samples:
        for entity_id, state in item.entities.items():
            hass.states.async_set(entity_id, state.state, state.attributes)
        result = await strategy.calculate(hass.states.get(primary))
        assert result is not None
        assert float(result) == pytest.approx(candidate.estimate_power(item), abs=0.001)


def _runtime_samples(models: ModuleType) -> list[Any]:
    primary, battery, status = "vacuum.robot", "sensor.battery", "sensor.activity"
    samples = []
    for activity, power in (
        ("sleeping", 3.5),
        ("washing", 22),
        ("drying", 7),
        ("auto_emptying", 600),
        ("cleaning", 0.3),
    ):
        for _ in range(5):
            attrs = {
                "vacuum_state": activity,
                "washing": activity == "washing",
                "drying": activity == "drying",
                "auto_empty_status": activity == "auto_emptying",
                "battery_level": 50,
            }
            samples.append(
                models.RecordingSample(
                    len(samples),
                    power,
                    {
                        primary: models.RecordedEntityState("cleaning" if activity == "cleaning" else "docked", attrs),
                        battery: models.RecordedEntityState("50", {}),
                        status: models.RecordedEntityState(activity, {}),
                    },
                )
            )
    for level in range(20, 81, 10):
        for _ in range(3):
            samples.append(
                models.RecordingSample(
                    len(samples),
                    50 - level / 2,
                    {
                        primary: models.RecordedEntityState(
                            "docked",
                            {
                                "vacuum_state": "charging",
                                "washing": False,
                                "drying": False,
                                "auto_empty_status": False,
                                "battery_level": level,
                            },
                        ),
                        battery: models.RecordedEntityState(str(level), {}),
                        status: models.RecordedEntityState("charging", {}),
                    },
                )
            )
    return samples
