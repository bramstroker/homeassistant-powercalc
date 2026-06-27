# Install development version

Install the latest development version of Powercalc by selecting the `dev` release in HACS.

## HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bramstroker&repository=homeassistant-powercalc)

1. Click the button above to open the Powercalc HACS repository.
2. Click the three-dot menu in the top right corner and select **Redownload**.
3. Select the `dev` release.
4. Click **Install**.
5. Restart Home Assistant.

!!! note

    When you install a later stable release, HACS replaces the `dev` version with that release.

## Developer tools action

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=update.install)

You can also install `dev` with the `update.install` action:

1. Click the button above to open the `update.install` action.
2. Select the Powercalc update entity as the target.
3. Enable **Version** and enter `dev`.
4. Perform the action.
5. Restart Home Assistant.
