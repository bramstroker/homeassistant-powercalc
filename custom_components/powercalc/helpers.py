import os;
from .const import MANUFACTURER_DIRECTORY_MAPPING

def get_light_model_directory(manufacturer: str, model: str) -> str:
    manufacturer_directory = MANUFACTURER_DIRECTORY_MAPPING.get(manufacturer) or manufacturer

    return os.path.join(
        os.path.dirname(__file__),
        f'data/{manufacturer_directory}/{model}'
    )