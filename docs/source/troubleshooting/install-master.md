# Install master

HACS no longer supports installing from the master branch.
If no new version of PowerCalc has been released yet and you need to test the latest functionality, you can update manually by following these steps:

1. Download the ZIP file from this URL: https://github.com/bramstroker/homeassistant-powercalc/archive/refs/heads/master.zip
2. Extract the contents of the ZIP.
3. Copy the custom_components/powercalc folder from the ZIP into your Home Assistant's config/custom_components/powercalc directory, replacing the existing files.
4. Restart Home Assistant to apply the latest improvements and updates.

!!! note

    Don't worry, next time a new version is released and you install it, HACS will update PowerCalc to the latest version, overwritting your temporary modifications.
