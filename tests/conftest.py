import pytest
from homeassistant import loader


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield

# def mock_integration(hass, module, built_in=True):
#     """Mock an integration."""
#     integration = loader.Integration(
#         hass,
#         f"{loader.PACKAGE_BUILTIN}.{module.DOMAIN}"
#         if built_in
#         else f"{loader.PACKAGE_CUSTOM_COMPONENTS}.{module.DOMAIN}",
#         None,
#         module.mock_manifest(),
#     )

#     def mock_import_platform(platform_name):
#         raise ImportError(
#             f"Mocked unable to import platform '{platform_name}'",
#             name=f"{integration.pkg_path}.{platform_name}",
#         )

#     integration._import_platform = mock_import_platform

#     #_LOGGER.info("Adding mock integration: %s", module.DOMAIN)
#     hass.data.setdefault(loader.DATA_INTEGRATIONS, {})[module.DOMAIN] = integration
#     hass.data.setdefault(loader.DATA_COMPONENTS, {})[module.DOMAIN] = module

#     return integration
    