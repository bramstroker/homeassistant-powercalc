import json
import os

from homeassistant.core import HomeAssistant

from custom_components.powercalc.power_profile.error import LibraryLoadingError
from custom_components.powercalc.power_profile.loader.protocol import Loader
from custom_components.powercalc.power_profile.power_profile import DeviceType

BUILT_IN_DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../../data")
LEGACY_CUSTOM_DATA_DIRECTORY = "powercalc-custom-models"
CUSTOM_DATA_DIRECTORY = "powercalc/profiles"


class LocalLoader(Loader):
    def __init__(self, hass: HomeAssistant) -> None:
        self._manufacturer_device_types: dict[str, list] | None = None
        self._model_aliases: dict[str, dict[str, str]] = {}
        self._data_directories: list[str] = [
            d
            for d in (
                os.path.join(hass.config.config_dir, CUSTOM_DATA_DIRECTORY),
                os.path.join(hass.config.config_dir, LEGACY_CUSTOM_DATA_DIRECTORY),
                os.path.join(os.path.dirname(__file__), "../../custom_data"),
                #BUILT_IN_DATA_DIRECTORY,
            )
            if os.path.exists(d)
        ]

    async def initialize(self) -> None:
        pass

    async def get_manufacturer_listing(self, device_type: DeviceType | None) -> set[str]:
        """Get listing of available manufacturers."""

        if self._manufacturer_device_types is None:
            with open(
                os.path.join(BUILT_IN_DATA_DIRECTORY, "manufacturer_device_types.json"),
            ) as file:
                self._manufacturer_device_types = json.load(file)

        manufacturers: set[str] = set()
        for data_dir in self._data_directories:
            for manufacturer in next(os.walk(data_dir))[1]:
                if (
                        device_type
                        and data_dir == BUILT_IN_DATA_DIRECTORY
                        and device_type not in self._manufacturer_device_types.get(manufacturer, [])
                ):
                    continue

                manufacturers.add(manufacturer)
        return manufacturers

    async def get_model_listing(self, manufacturer: str, device_type: DeviceType | None) -> set[str]:
        """Get listing of available models for a given manufacturer."""
        """Lazy loads a list of power profiles per manufacturer.

                Using the following lookup fallback mechanism:
                 - check in user defined directory (config/powercalc-custom-models)
                 - check in alternative user defined directory (config/custom_components/powercalc/custom_data)
                 - check in built-in directory (config/custom_components/powercalc/data)
                """

        models: set[str] = set()
        for data_dir in self._data_directories:
            manufacturer_dir = os.path.join(data_dir, manufacturer)
            if not os.path.exists(manufacturer_dir):
                continue
            for model in os.listdir(manufacturer_dir):
                if model[0] in [".", "@"]:
                    continue
                with open(os.path.join(manufacturer_dir, model, "model.json")) as f:
                    model_json = json.load(f)
                supported_device_type = DeviceType(model_json.get("device_type", DeviceType.LIGHT))
                if device_type and device_type != supported_device_type:
                    continue
                models.add(model)
                self._model_aliases[manufacturer_dir] = model_json.get("aliases", [])
        return models

    async def load_model(self, manufacturer: str, model: str, directory: str | None) -> tuple[dict, str] | None:
        base_dir = directory
        if not directory:
            for data_dir in self._data_directories:
                base_dir = os.path.join(
                    data_dir,
                    manufacturer.lower(),
                    model,
                )
                if not os.path.exists(base_dir):
                    base_dir = None
                    continue

        if base_dir is None:
            return None

        model_json_path = os.path.join(base_dir, "model.json")
        if not model_json_path or not os.path.exists(model_json_path):
            raise LibraryLoadingError(f"model.json not found for {manufacturer} {model}")

        with open(model_json_path) as file:
            return json.load(file), base_dir

    async def find_model(self, manufacturer: str, search: set[str]) -> str | None:
        for data_dir in self._data_directories:
            manufacturer_dir = os.path.join(data_dir, manufacturer)
            if not os.path.exists(manufacturer_dir):
                continue
            model_dirs = os.listdir(manufacturer_dir)
            for model in search:
                if model in model_dirs:
                    return model

        return None
