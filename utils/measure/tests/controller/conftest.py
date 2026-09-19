from unittest.mock import MagicMock

from measure.home_assistant.client import HomeAssistantManager
import pytest


@pytest.fixture
def hass_client() -> MagicMock:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_config.return_value = {}
    return client
