from __future__ import annotations

from collections.abc import Iterator
import os
import shutil
from typing import Any, Protocol, cast
from unittest.mock import MagicMock, patch

from decouple import UndefinedValueError
from measure.cli.environment import CliEnvironment
from measure.const import (
    PROJECT_DIR,
    QUESTION_DUMMY_LOAD,
    QUESTION_GENERATE_MODEL_JSON,
    QUESTION_MEASURE_DEVICE,
    QUESTION_MODEL_ID,
    QUESTION_MODEL_NAME,
    QUESTION_SELECTED_MEASURE_TYPE,
)
from measure.controller.light.const import LutMode
from measure.runner.const import QUESTION_GZIP, QUESTION_MODE, QUESTION_MULTIPLE_LIGHTS, QUESTION_NUM_LIGHTS
import pytest


class MockConfigFactory(Protocol):
    def __call__(
        self,
        config_values: dict[str, Any] | None = None,
        *,
        set_question_defaults: bool = True,
        question_defaults: dict[str, Any] | None = None,
    ) -> MagicMock: ...


@pytest.fixture(autouse=True)
def _mock_sleep() -> None:
    with patch("time.sleep", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _mock_hass_config() -> Iterator[None]:
    with patch("homeassistant_api.Client.get_config", return_value={}):
        yield


@pytest.fixture(autouse=True)
def clean_export_directory() -> None:
    export_dir = os.path.join(PROJECT_DIR, "export")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    shutil.rmtree(export_dir)
    yield


@pytest.fixture
def mock_config_factory() -> MockConfigFactory:
    def _mock_config(
        config_values: dict[str, Any] | None = None,
        set_question_defaults: bool = True,
        question_defaults: dict[str, Any] | None = None,
    ) -> MagicMock:
        default_config_values = {
            "selected_light_controller": "dummy",
            "selected_power_meter": "dummy",
            "selected_media_controller": "dummy",
            "selected_charging_controller": "dummy",
            "selected_fan_controller": "dummy",
            "selected_measure_type": None,
            "min_brightness": 1,
            "max_brightness": 255,
            "min_sat": 1,
            "max_sat": 255,
            "min_hue": 1,
            "max_hue": 65535,
            "ct_bri_steps": 5,
            "ct_mired_steps": 10,
            "bri_bri_steps": 1,
            "hs_bri_precision": 1,
            "hs_bri_steps": 32,
            "hs_hue_precision": 1,
            "hs_hue_steps": 2731,
            "hs_sat_precision": 1,
            "hs_sat_steps": 32,
            "effect_bri_steps": 40,
            "measure_time_effect": 10,
            "measure_time_effect_min": 10,
            "measure_time_effect_convergence_window": 10,
            "measure_time_effect_convergence_abs": 0.1,
            "measure_time_effect_convergence_rel": 0.01,
            "sleep_time": 0,
            "sleep_initial": 0,
            "sleep_standby": 0,
            "sleep_time_sample": 0,
            "sleep_time_hue": 0,
            "sleep_time_sat": 0,
            "sleep_time_ct": 0,
            "sleep_time_effect_change": 0,
            "sleep_time_nudge": 0,
            "pulse_time_nudge": 0,
            "max_retries": 5,
            "max_nudges": 0,
            "resume": False,
        }
        if config_values is not None:
            default_config_values.update(config_values)
        if set_question_defaults:
            default_config_values.update(
                {
                    QUESTION_GENERATE_MODEL_JSON: True,
                    QUESTION_DUMMY_LOAD: False,
                    QUESTION_MODEL_NAME: "Test model",
                    QUESTION_MODEL_ID: "LCT010",
                    QUESTION_MEASURE_DEVICE: "Shelly Plug S",
                    QUESTION_GZIP: True,
                    QUESTION_MULTIPLE_LIGHTS: False,
                    QUESTION_NUM_LIGHTS: 1,
                    QUESTION_SELECTED_MEASURE_TYPE: "Light bulb(s)",
                    QUESTION_MODE: {LutMode.BRIGHTNESS},
                    **(question_defaults or {}),
                },
            )

        real_config = CliEnvironment()
        mock_instance = MagicMock(spec=CliEnvironment)
        mock_instance.get_conf_value = MagicMock()
        mock_instance.get_conf_value.side_effect = lambda k: default_config_values.get(k.lower())

        properties = {prop for prop in dir(CliEnvironment) if isinstance(getattr(CliEnvironment, prop, None), property)}
        for prop in properties:
            try:
                default_val = getattr(real_config, prop)
            except UndefinedValueError:
                default_val = None
            setattr(mock_instance, prop, default_config_values.get(prop, default_val))

        return mock_instance

    return cast(MockConfigFactory, _mock_config)


class MockRequestsGetFactory(Protocol):
    def __call__(self, responses: dict[str, tuple[object, int]]) -> patch: ...


@pytest.fixture
def mock_requests_get_factory() -> Iterator[MockRequestsGetFactory]:
    """
    Mock the requests.get function to return the specified responses.
    """

    mock_requests_get_patchers: list[Any] = []

    def factory(responses: dict[str, tuple[object, int]]) -> patch:
        class MockResponse:
            def __init__(self, json_data: object, status_code: int) -> None:
                self.json_data = json_data
                self.status_code = status_code

            def json(self) -> object:
                return self.json_data

        def mock_requests_get(url: str, *args: object, **kwargs: object) -> MockResponse:
            response_data, status_code = responses.get(url, ({"error": "Unknown endpoint"}, 404))

            return MockResponse(response_data, status_code)

        mock_request = patch("requests.get", side_effect=mock_requests_get)
        mock_request.start()
        mock_requests_get_patchers.append(mock_request)
        return mock_request

    yield factory

    for mock_request in mock_requests_get_patchers:
        mock_request.stop()


@pytest.fixture()
def export_path(tmp_path: str) -> str:
    export_dir = tmp_path / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    return str(export_dir)
