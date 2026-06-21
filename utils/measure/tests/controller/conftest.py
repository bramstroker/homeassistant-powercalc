from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _mock_hass_config() -> Iterator[None]:
    with patch("homeassistant_api.Client.get_config", return_value={}):
        yield
