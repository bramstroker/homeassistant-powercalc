from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from measure.config import MeasureConfig
from measure.const import PROJECT_DIR
from measure.controller.light.const import ColorMode


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
        if config_values is None:
            config_values = {
                "selected_light_controller": "dummy",
                "selected_power_meter": "dummy",
                "selected_media_controller": "dummy",
                "selected_charging_controller": "dummy",
                "sleep_time": 0,
                "sleep_initial": 0,
                "sleep_standby": 0,
                "resume": False,
                "min_brightness": 0,
                "max_brightness": 255,
                "bri_bri_steps": 1,
                "sample_count": 1,
                "sleep_time_sample": 0,
            }
        if set_question_defaults:
            config_values = {
                "generate_model_json": True,
                "dummy_load": False,
                "model_name": "Test model",
                "measure_device": "Shelly Plug S",
                "gzip": True,
                "multiple_lights": False,
                "num_lights": 1,
                "selected_measure_type": "Light bulb(s)",
                "color_mode": {ColorMode.BRIGHTNESS},
                **(question_defaults or {}),
                **config_values,
            }

        mock_instance = mock.return_value
        mock_instance.get_conf_value = MagicMock()
        mock_instance.get_conf_value.side_effect = lambda k: config_values.get(k.lower(), None)

        properties = {prop for prop in dir(MeasureConfig) if isinstance(getattr(MeasureConfig, prop, None), property)}
        for prop in properties:
            setattr(mock_instance, prop, config_values.get(prop, None))

        return mock_instance

    return _mock_config
