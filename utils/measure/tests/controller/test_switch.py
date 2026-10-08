from types import SimpleNamespace
from unittest.mock import MagicMock, call

from homeassistant_api.errors import HomeassistantAPIError
from measure.controller.errors import ControllerError
from measure.controller.switch.hass import HassSwitchController
from measure.controller.switch.spec import HassMultiSwitchControllerSpec, HassSwitchControllerSpec
from measure.home_assistant.client import HomeAssistantManager
from pydantic import ValidationError
import pytest


def test_switch_controller_measures_each_relay_and_restores_original_states() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    states = {"switch.one": "on", "switch.two": "off"}
    home_assistant.get_state.side_effect = lambda entity_id: SimpleNamespace(state=states[entity_id])
    controller = HassSwitchController(home_assistant, list(states))

    controller.remember_states()
    controller.set_states("switch.two")
    states.update({"switch.one": "off", "switch.two": "on"})
    controller.verify_states("switch.two")
    controller.restore_states()

    assert home_assistant.trigger_service.call_args_list == [
        call("switch", "turn_off", entity_id="switch.one"),
        call("switch", "turn_on", entity_id="switch.two"),
        call("switch", "turn_on", entity_id="switch.one"),
        call("switch", "turn_off", entity_id="switch.two"),
    ]
    assert controller.initial_states == {}


def test_switch_controller_rejects_unknown_state() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_state.return_value = SimpleNamespace(state="unavailable")
    controller = HassSwitchController(home_assistant, ["switch.one"])

    with pytest.raises(ControllerError, match="unusable state"):
        controller.remember_states()


def test_switch_controller_reports_read_and_verification_failures() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    controller = HassSwitchController(home_assistant, ["switch.one"])
    home_assistant.get_state.side_effect = HomeassistantAPIError("offline")
    with pytest.raises(ControllerError, match="Could not read"):
        controller.read_state("switch.one")

    home_assistant.get_state.side_effect = None
    home_assistant.get_state.return_value = SimpleNamespace(state="off")
    with pytest.raises(ControllerError, match="did not reach"):
        controller.verify_states("switch.one")


def test_switch_controller_reports_service_failure() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.trigger_service.side_effect = HomeassistantAPIError("offline")
    controller = HassSwitchController(home_assistant, ["switch.one"])

    with pytest.raises(ControllerError, match="Could not turn on"):
        controller.set_state("switch.one", True)


def test_switch_controller_can_enable_all_relays() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    controller = HassSwitchController(home_assistant, ["switch.one", "switch.two"])

    controller.set_states(all_on=True)

    assert home_assistant.trigger_service.call_args_list == [
        call("switch", "turn_on", entity_id="switch.one"),
        call("switch", "turn_on", entity_id="switch.two"),
    ]


def test_switch_specs_expose_entity_ids_and_reject_duplicates() -> None:
    assert HassSwitchControllerSpec(entity_id="switch.one").entity_ids == ["switch.one"]
    with pytest.raises(ValidationError, match="unique"):
        HassMultiSwitchControllerSpec(entity_ids=["switch.one", "switch.one"])


def test_switch_controller_restores_remaining_relays_after_failure() -> None:
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_state.return_value = SimpleNamespace(state="off")
    home_assistant.trigger_service.side_effect = [HomeassistantAPIError("unavailable"), None]
    controller = HassSwitchController(home_assistant, ["switch.one", "switch.two"])
    controller.remember_states()

    with pytest.raises(ControllerError, match="Could not restore all"):
        controller.restore_states()

    assert home_assistant.trigger_service.call_count == 2
