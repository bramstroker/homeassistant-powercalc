from homeassistant_api.errors import HomeassistantAPIError

from measure.controller.errors import ControllerError
from measure.home_assistant.client import HomeAssistantManager


class HassSwitchController:
    """Control a set of relays while retaining their initial states for cleanup."""

    def __init__(self, home_assistant: HomeAssistantManager, entity_ids: list[str]) -> None:
        self.client = home_assistant
        self.entity_ids = entity_ids
        self.initial_states: dict[str, bool] = {}

    def read_state(self, entity_id: str) -> bool:
        try:
            state = str(self.client.get_state(entity_id=entity_id).state).lower()
        except HomeassistantAPIError as error:
            raise ControllerError(f"Could not read {entity_id}: {error}") from error
        if state not in {"on", "off"}:
            raise ControllerError(f"Switch {entity_id} has unusable state {state!r}")
        return state == "on"

    def remember_states(self) -> None:
        self.initial_states = {entity_id: self.read_state(entity_id) for entity_id in self.entity_ids}

    def set_state(self, entity_id: str, on: bool) -> None:
        try:
            self.client.trigger_service("switch", "turn_on" if on else "turn_off", entity_id=entity_id)
        except HomeassistantAPIError as error:
            raise ControllerError(f"Could not turn {'on' if on else 'off'} {entity_id}: {error}") from error

    def set_states(self, active_entity_id: str | None = None, *, all_on: bool = False) -> None:
        for entity_id in self.entity_ids:
            if not all_on and entity_id != active_entity_id:
                self.set_state(entity_id, False)
        if all_on:
            for entity_id in self.entity_ids:
                self.set_state(entity_id, True)
        elif active_entity_id is not None:
            self.set_state(active_entity_id, True)

    def verify_states(self, active_entity_id: str | None = None, *, all_on: bool = False) -> None:
        for entity_id in self.entity_ids:
            expected = all_on or entity_id == active_entity_id
            if self.read_state(entity_id) != expected:
                raise ControllerError(f"Switch {entity_id} did not reach the requested state")

    def restore_states(self) -> None:
        errors: list[ControllerError] = []
        for entity_id, on in self.initial_states.items():
            try:
                self.set_state(entity_id, on)
            except ControllerError as error:
                errors.append(error)
        if errors:
            raise ControllerError("Could not restore all switch relays: " + "; ".join(str(error) for error in errors))
        self.initial_states.clear()
