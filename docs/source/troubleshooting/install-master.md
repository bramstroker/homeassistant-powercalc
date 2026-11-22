# Install development version

The `dev` release is the latest development build of Powercalc.

[![Open Powercalc in the Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=bramstroker&repository=homeassistant-powercalc&category=integration)

1. If Powercalc is new to your Home Assistant instance, [install it from the Marketplace](../quick-start.md#installation) first.
2. Go to **Settings → Devices & services → Marketplace** and select the Powercalc device. Enable the **Pre-release** entity, then turn on its switch.
3. Open Powercalc in the Marketplace using the button above. From the three-dot menu, select **Install another version**.
4. Select `dev` and confirm with **Install**.
5. Restart Home Assistant to apply the change.

To return to stable releases, turn off **Pre-release** and install the latest stable version from the Marketplace.

## Developer tools action

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=update.install)

You can also install `dev` with the `update.install` action once Powercalc is installed through the Marketplace.

1. Click the button above to open the `update.install` action.
2. Select the Powercalc update entity as the target.
3. Enable **Version** and enter `dev`.
4. Perform the action.
5. Restart Home Assistant.
