from __future__ import annotations

import os

from homeassistant.core import HomeAssistant

from ..aliases import MANUFACTURER_DIRECTORY_MAPPING, MODEL_DIRECTORY_MAPPING

CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"


class ProfileLibrary:
    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._data_directories: tuple[str] = (
            dir
            for dir in (
                os.path.join(hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
                os.path.join(os.path.dirname(__file__), "../custom_data"),
                os.path.join(os.path.dirname(__file__), "../data"),
            )
            if os.path.exists(dir)
        )

    def get_manufacturer_listing(self) -> list[str]:
        """Get listing of available manufacturers"""
        manufacturers: list[str] = []
        for data_dir in self._data_directories:
            manufacturers.extend(next(os.walk(data_dir))[1])
        return sorted(manufacturers)

    def get_model_listing(self, manufacturer: str) -> list[str]:
        """Get listing of available models for a given manufacturer"""
        models: list[str] = []
        for data_dir in self._data_directories:
            manufacturer_dir = os.path.join(data_dir, manufacturer)
            if not os.path.exists(manufacturer_dir):
                continue
            models.extend(os.listdir(manufacturer_dir))
        return sorted(models)

    def get_model_directory(self, manufacturer: str, model: str) -> str | None:
        """Get a directory for a model, walk through the available data directories"""

        manufacturer_directory = (
            MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer) or manufacturer
        ).lower()

        model_directory = model
        if isinstance(
            MODEL_DIRECTORY_MAPPING.get(manufacturer), dict
        ) and MODEL_DIRECTORY_MAPPING.get(manufacturer).get(model):
            model_directory = MODEL_DIRECTORY_MAPPING.get(manufacturer).get(model)

        for data_dir in self._data_directories:
            directory = os.path.join(data_dir, manufacturer_directory, model_directory)
            if os.path.exists(directory):
                return directory
        return None
