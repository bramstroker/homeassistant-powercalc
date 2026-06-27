# Install development version

HACS no longer supports selecting the master branch from the UI.
If no new version of PowerCalc has been released yet and you need to test the latest functionality, you can install the moving `dev` release from Home Assistant's actions tool:

1. Go to **Developer tools** > **Actions**.
2. Select the `update.install` action.
3. Select the Powercalc update entity as the target.
4. Enable **Version** and enter `dev`.
5. Perform the action.
6. Restart Home Assistant to apply the latest improvements and updates.

!!! note

    Don't worry, next time a new version is released and you install it, HACS will update PowerCalc to the latest version, overwriting your temporary modifications.

You can also install the master branch manually:

1. Download the ZIP file from this URL: [https://github.com/bramstroker/homeassistant-powercalc/archive/refs/heads/master.zip](https://github.com/bramstroker/homeassistant-powercalc/archive/refs/heads/master.zip)
2. Extract the contents of the ZIP.
3. Copy the custom_components/powercalc folder from the ZIP into your Home Assistant's config/custom_components/powercalc directory, replacing the existing files.
4. Restart Home Assistant to apply the latest improvements and updates.
