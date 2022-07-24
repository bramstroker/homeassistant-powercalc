from custom_components.powercalc.common import SourceEntity


def create_source_entity(
    platform: str, supported_color_modes=list[str]
) -> SourceEntity:
    return SourceEntity(
        "test",
        f"{platform}.test",
        platform,
        supported_color_modes=supported_color_modes,
    )
