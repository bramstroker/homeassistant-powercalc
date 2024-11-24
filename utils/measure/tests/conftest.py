from __future__ import annotations

import os
import shutil
from unittest.mock import MagicMock, patch

import pytest
from measure.const import PROJECT_DIR


@pytest.fixture(autouse=True)
def clean_export_directory() -> None:
    export_dir = os.path.join(PROJECT_DIR, "export")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    shutil.rmtree(export_dir)
    yield


@pytest.fixture
@patch("measure.config.MeasureConfig")
def mock_config(mock) -> MagicMock:
    # Create an instance of the mocked class
    mock_instance = mock.return_value

    # Mock specific property values
    mock_instance.min_brightness = 100
    mock_instance.max_brightness = 200
    mock_instance.min_sat = 10
    mock_instance.max_sat = 20

    return mock_instance


type ConfigValueType = str | int | bool | set


class MockConfig:
    _instance = None  # Class-level attribute to hold the singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def clear(self) -> None:
        self.values.clear()

    def set_values(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, var: str, default: str | None = None, cast: int | None = None) -> str:
        return self.values.get(var, default)
