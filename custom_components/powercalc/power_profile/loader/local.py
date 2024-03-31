import json
import os

from homeassistant.core import HomeAssistant

from custom_components.powercalc.aliases import MANUFACTURER_DIRECTORY_MAPPING
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

BUILT_IN_DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../data")
LEGACY_CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"
CUSTOM_DATA_DIRECTORY = "powercalc/models"


class LocalLoader(Loader):
    def __init__(self, hass: HomeAssistant) -> None:
        self._manufacturer_device_types: dict[str, list] | None = None
        self._data_directories: list[str] = [
            d
            for d in (
                os.path.join(hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
                os.path.join(hass.config.config_dir, LEGACY_CUSTOM_DATA_DIRECTORY),
                os.path.join(os.path.dirname(__file__), "../../custom_data"),
                BUILT_IN_DATA_DIRECTORY,
            )
            if os.path.exists(d)
        ]

    def get_manufacturer_listing(self, device_type: DeviceType | None) -> list[str]:
        """Get listing of available manufacturers."""

        if self._manufacturer_device_types is None:
            with open(
                os.path.join(BUILT_IN_DATA_DIRECTORY, "manufacturer_device_types.json"),
            ) as file:
                self._manufacturer_device_types = json.load(file)

        manufacturers: list[str] = []
        for data_dir in self._data_directories:
            for manufacturer in next(os.walk(data_dir))[1]:
                if (
                        device_type
                        and data_dir == BUILT_IN_DATA_DIRECTORY
                        and device_type not in self._manufacturer_device_types.get(manufacturer, [])
                ):
                    continue

                manufacturers.append(manufacturer)
        return manufacturers

    def get_model_listing(self, manufacturer: str) -> list[str]:
        """Get listing of available models for a given manufacturer."""
        if manufacturer in MANUFACTURER_DIRECTORY_MAPPING:
            manufacturer = str(MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer))
        manufacturer = manufacturer.lower()

        models: list[str] = []
        for data_dir in self._data_directories:
            manufacturer_dir = os.path.join(data_dir, manufacturer)
            if not os.path.exists(manufacturer_dir):
                continue
            model_dirs = [f for f in os.listdir(manufacturer_dir) if f[0] not in [".", "@"]]
            models.extend(model_dirs)
        return models

    def load_model(self, manufacturer: str, model: str, directory: str | None) -> tuple[dict, str] | None:
        base_dir = directory
        if not directory:
            for data_dir in self._data_directories:
                base_dir = os.path.join(
                    data_dir,
                    manufacturer.lower(),
                    model,
                )
                if not os.path.exists(base_dir):
                    continue

        if base_dir is None:
            return None

        model_json_path = os.path.join(base_dir, "model.json")
        if model_json_path is None:
            raise FileNotFoundError(f"model.json not found for {manufacturer} {model}")

        with open(model_json_path) as file:
            return json.load(file), base_dir
