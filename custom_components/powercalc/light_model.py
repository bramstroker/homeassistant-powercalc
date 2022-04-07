import json
import logging
import os
from typing import Optional

from homeassistant.helpers.typing import HomeAssistantType

from .const import (
    MANUFACTURER_DIRECTORY_MAPPING,
    MODE_FIXED,
    MODE_LINEAR,
    MODEL_DIRECTORY_MAPPING,
)
from .errors import ModelNotSupported, UnsupportedMode

_LOGGER = logging.getLogger(__name__)

CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"


class LightModel:
    def __init__(
        self,
        hass: HomeAssistantType,
        manufacturer: str,
        model: str,
        custom_model_directory: str,
    ):
        self._manufacturer = manufacturer
        self._model = model
        self._lut_subdirectory = None

        # Support multiple LUT in subdirectories
        if "/" in model:
            model_parts = model.split("/", 1)
            self._model = model_parts[0]
            self._lut_subdirectory = model_parts[1]

        self._model = self._model.replace("#slash#", "/")
        self._custom_model_directory = custom_model_directory
        self._hass = hass
        self._directory: str = None
        self.load_model_manifest()

    def load_model_manifest(self) -> dict:
        """Load the model.json file data containing information about the light model"""

        model_directory = self.get_directory()
        file_path = os.path.join(model_directory, "model.json")
        if not os.path.exists(file_path):
            raise ModelNotSupported(
                f"Model not found in library (manufacturer: {self._manufacturer}, model: {self._model})"
            )

        _LOGGER.debug(f"Loading {file_path}")
        json_file = open(file_path)
        self._json_data = json.load(json_file)

        if self._lut_subdirectory:
            subdirectory = os.path.join(self._directory, self._lut_subdirectory)
            _LOGGER.debug(f"Loading LUT directory {self._directory}")
            if not os.path.exists(file_path):
                raise ModelNotSupported(
                    f"LUT subdirectory not found (manufacturer: {self._manufacturer}, model: {self._model})"
                )

            # When the sub LUT directory also has a model.json (not required), merge this json into the main model.json data.
            file_path = os.path.join(subdirectory, "model.json")
            if os.path.exists(file_path):
                json_file = open(file_path)
                self._json_data = {**self._json_data, **json.load(json_file)}

        return self._json_data

    def get_directory(self) -> str:
        """
        Get the light model directory.
        Using the following fallback mechanism:
         - custom_model_directory defined on sensor configuration
         - check in user defined directory (config/powercalc-custom-models)
         - check in alternative user defined directory (config/custom_components/powercalc/custom_data)
         - check in buildin directory (config/custom_components/powercalc/data)
        """

        # Only fetch directory once
        if self._directory:
            return self._directory

        if self._custom_model_directory:
            return self._custom_model_directory

        manufacturer_directory = (
            MANUFACTURER_DIRECTORY_MAPPING.get(self._manufacturer) or self._manufacturer
        ).lower()

        model_directory = self._model
        if isinstance(
            MODEL_DIRECTORY_MAPPING.get(self._manufacturer), dict
        ) and MODEL_DIRECTORY_MAPPING.get(self._manufacturer).get(self._model):
            model_directory = MODEL_DIRECTORY_MAPPING.get(self._manufacturer).get(
                self._model
            )

        data_directories = (
            os.path.join(self._hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
            os.path.join(os.path.dirname(__file__), "custom_data"),
            os.path.join(os.path.dirname(__file__), "data"),
        )
        for data_dir in data_directories:
            model_data_dir = os.path.join(
                data_dir,
                f"{manufacturer_directory}/{model_directory}",
            )
            if os.path.exists(model_data_dir):
                self._directory = model_data_dir
                return self._directory

        raise ModelNotSupported(
            f"Model not found in library (manufacturer: {self._manufacturer}, model: {self._model})"
        )

    def get_lut_directory(self) -> str:
        model_directory = self.get_directory()
        if self._lut_subdirectory:
            model_directory = os.path.join(model_directory, self._lut_subdirectory)
        return model_directory

    @property
    def manufacturer(self) -> str:
        return self._manufacturer

    @property
    def model(self) -> str:
        return self._model

    @property
    def name(self) -> str:
        return self._json_data.get("name")

    @property
    def standby_power(self) -> float:
        return self._json_data.get("standby_power") or 0

    @property
    def supported_modes(self) -> list:
        return self._json_data.get("supported_modes") or []

    @property
    def linear_mode_config(self) -> Optional[dict]:
        if not self.is_mode_supported(MODE_LINEAR):
            raise UnsupportedMode(
                f"Mode linear is not supported by model: {self._model}"
            )
        return self._json_data.get("linear_config")

    @property
    def fixed_mode_config(self) -> Optional[dict]:
        if not self.is_mode_supported(MODE_FIXED):
            raise UnsupportedMode(
                f"Mode fixed is not supported by model: {self._model}"
            )
        return self._json_data.get("fixed_config")

    @property
    def is_autodiscovery_allowed(self) -> bool:
        return self._lut_subdirectory is None

    def is_mode_supported(self, mode: str) -> bool:
        return mode in self.supported_modes
