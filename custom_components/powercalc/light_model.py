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
        self._custom_model_directory = custom_model_directory
        self._hass = hass
        self._json_data = self.load_model_manifest()

    def load_model_manifest(self) -> dict:
        file_path = os.path.join(self.get_directory(), "model.json")
        if not os.path.exists(file_path):
            raise ModelNotSupported(
                f"Model not found in library (manufacturer: {self._manufacturer}, model: {self._model})"
            )

        _LOGGER.debug(f"Loading {file_path}")
        json_file = open(file_path)
        return json.load(json_file)

    def get_directory(self) -> str:
        """
        Get the light model directory.
        Using the following fallback mechanism:
         - custom_model_directory defined on sensor configuration
         - check in user defined directory (config/powercalc-custom-models)
         - check in buildin directory (config/custom_components/data)
        """

        if self._custom_model_directory:
            return self._custom_model_directory

        manufacturer_directory = (
            MANUFACTURER_DIRECTORY_MAPPING.get(self._manufacturer) or self._manufacturer
        )

        model_directory = self._model
        if isinstance(
            MODEL_DIRECTORY_MAPPING.get(self._manufacturer), dict
        ) and MODEL_DIRECTORY_MAPPING.get(self._manufacturer).get(self._model):
            model_directory = MODEL_DIRECTORY_MAPPING.get(self._manufacturer).get(
                self._model
            )

        custom_model_data_dir = os.path.join(
            self._hass.config.config_dir,
            CUSTOM_DATA_DIRECTORY,
            f"{manufacturer_directory}/{model_directory}",
        )
        if os.path.exists(custom_model_data_dir):
            return custom_model_data_dir

        model_data_dir = os.path.join(
            os.path.dirname(__file__),
            f"data/{manufacturer_directory}/{model_directory}",
        )
        if os.path.exists(model_data_dir):
            return model_data_dir

        raise ModelNotSupported(
            f"Model not found in library (manufacturer: {self._manufacturer}, model: {self._model})"
        )

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
    def standby_usage(self) -> float:
        return self._json_data.get("standby_usage") or 0

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

    def is_mode_supported(self, mode: str):
        return mode in self.supported_modes
