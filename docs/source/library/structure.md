# Library structure

Each power profile has it's own subdirectory `{manufacturer}/{modelid}`. i.e. signify/LCT010, containing a `model.json` file and optionally CSV files for the LUT calculation strategy.

## model.json

Every profile MUST contain a `model.json` file which defines the supported calculation modes and other configuration.
See the [json schema](https://github.com/bramstroker/homeassistant-powercalc/blob/master/profile_library/model_schema.json) how the file must be structured.

Examples for different device types can be found in the [device types](device-types/index.md) section.

You can use `aliases` to define alternative model names, which will be used during discovery.
This can be helpful when same model is reported differently depending on the integration. For example, the same light bulb could be reported differently by the Hue integration compared to the deCONZ integration.
