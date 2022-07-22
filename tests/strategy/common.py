from custom_components.powercalc.common import SourceEntity

def create_source_entity(platform: str) -> SourceEntity:
    return SourceEntity(
        "test",
        f"{platform}.test",
        platform
    )