from __future__ import annotations

import os
import shutil
from unittest.mock import patch

import pytest
from measure.const import PROJECT_DIR


@pytest.fixture(autouse=True)
def clean_export_directory() -> None:
    export_dir = os.path.join(PROJECT_DIR, "export")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    shutil.rmtree(export_dir)
    yield


@pytest.fixture(scope="session", autouse=True)
@patch("decouple.config")
def mock_config_init(mock_config) -> None:
    mock_config_instance = MockConfig()

    def mock_config_side_effect(var: str, default: ConfigValueType | None = None, cast: int | None = None) -> ConfigValueType:
        return mock_config_instance.get(var, default, cast)

    mock_config.side_effect = mock_config_side_effect


@pytest.fixture(scope="session")
def mock_config() -> MockConfig:
    return MockConfig()


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
