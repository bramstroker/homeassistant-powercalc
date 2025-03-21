from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from typing import Any, Protocol
from unittest.mock import MagicMock, patch

import pytest
from decouple import UndefinedValueError
from measure.config import MeasureConfig
from measure.const import PROJECT_DIR
from measure.controller.light.const import LutMode


@pytest.fixture(autouse=True)
def clean_export_directory() -> None:
    export_dir = os.path.join(PROJECT_DIR, "export")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    shutil.rmtree(export_dir)
    yield


@pytest.fixture
def mock_config_factory() -> Callable[[dict[str, Any]], MagicMock]:
    @patch("measure.config.MeasureConfig", autospec=True)
    def _mock_config(
        mock: MagicMock,
        config_values: dict | None = None,
        set_question_defaults: bool = True,
        question_defaults: dict | None = None,
    ) -> MagicMock:
        default_config_values = {
            "selected_light_controller": "dummy",
            "selected_power_meter": "dummy",
            "selected_media_controller": "dummy",
            "selected_charging_controller": "dummy",
            "sleep_time": 0,
            "sleep_initial": 0,
            "sleep_standby": 0,
            "sleep_time_sample": 0,
            "resume": False,
        }
        if config_values is not None:
            default_config_values.update(config_values)
        if set_question_defaults:
            default_config_values.update(
                {
                    "generate_model_json": True,
                    "dummy_load": False,
                    "model_name": "Test model",
                    "measure_device": "Shelly Plug S",
                    "gzip": True,
                    "multiple_lights": False,
                    "num_lights": 1,
                    "selected_measure_type": "Light bulb(s)",
                    "mode": {LutMode.BRIGHTNESS},
                    **(question_defaults or {}),
                },
            )

        real_config = MeasureConfig()
        mock_instance = mock.return_value
        mock_instance.get_conf_value = MagicMock()
        mock_instance.get_conf_value.side_effect = lambda k: default_config_values.get(k.lower(), real_config.get_conf_value(k))

        properties = {prop for prop in dir(MeasureConfig) if isinstance(getattr(MeasureConfig, prop, None), property)}
        for prop in properties:
            try:
                default_val = getattr(real_config, prop)
            except UndefinedValueError:
                default_val = None
            setattr(mock_instance, prop, default_config_values.get(prop, default_val))

        return mock_instance

    return _mock_config


class MockRequestsGetFactory(Protocol):
    def __call__(self, responses: dict[str, tuple[dict, int]]) -> patch: ...


@pytest.fixture
def mock_requests_get_factory() -> MockRequestsGetFactory:
    """
    Mock the requests.get function to return the specified responses.
    """

    def factory(responses: dict[str, tuple[dict, int]]) -> patch:
        def mock_requests_get(url: str, *args, **kwargs):  # noqa
            response_data, status_code = responses.get(url, ({"error": "Unknown endpoint"}, 404))

            # Create a mock response object
            class MockResponse:
                def __init__(self, json_data: dict, status_code: int) -> None:
                    self.json_data = json_data
                    self.status_code = status_code

                def json(self) -> dict:
                    return self.json_data

            return MockResponse(response_data, status_code)

        mock_request = patch("requests.get", side_effect=mock_requests_get)
        mock_request.start()
        return mock_request

    return factory


@pytest.fixture()
def export_path(tmp_path: str) -> str:
    export_dir = tmp_path / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    return str(export_dir)
