# Library structure

Each power profile has it's own subdirectory `{manufacturer}/{modelid}`. i.e. signify/LCT010, containing a `model.json` file and optionally CSV files for the LUT calculation strategy.

## model.json

Every profile MUST contain a `model.json` file which defines the supported calculation modes and other configuration.
See the [json schema](https://github.com/bramstroker/homeassistant-powercalc/blob/master/profile_library/model_schema.json) how the file must be structured.

Examples for different device types can be found in the [device types](device-types/index.md) section.

You can use `aliases` to define alternative model names, which will be used during discovery.
This can be helpful when same model is reported differently depending on the integration. For example, the same light bulb could be reported differently by the Hue integration compared to the deCONZ integration.

## Sub profiles

Some profiles might have multiple profiles. This is useful when a device has different power consumption based on the state of the device.
This can be used for example for different infrared modes of a light.

Each sub profile has it's own subdirectory `{manufacturer}/{modelid}/{subprofile}`, which contains a `model.json` file.
You can also define `sub_profile_select` in the main `model.json` to automatically select the sub profile based on the state of the device.
When no `sub_profile_select` is defined, the user will be asked to select the sub profile during discovery.

Examples:

- [lifx/LIFX A19 Night Vision](https://github.com/bramstroker/homeassistant-powercalc/tree/master/profile_library/lifx/LIFX%20A19%20Night%20Vision)
- [eufy/T8400](https://github.com/bramstroker/homeassistant-powercalc/tree/master/profile_library/eufy/T8400)
