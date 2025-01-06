# Library structure

The library is structured in a multi level tree structure. The top level is the manufacturer, followed by the model id and optionally sub profiles.
Manufacturer directory must hae a `manufacturer.json` file which contains the manufacturer name and optionally aliases.
Each power profile has it's own subdirectory `{manufacturer}/{modelid}`. i.e. signify/LCT010, containing a `model.json` file and optionally CSV files for the LUT calculation strategy.

## model.json

Every profile MUST contain a `model.json` file which defines the supported calculation modes and other configuration.
See the [json schema](https://github.com/bramstroker/homeassistant-powercalc/blob/master/profile_library/model_schema.json) how the file must be structured.

Required fields are:

- `name`: The name of the device (this is only used in the [Library](https://library.powercalc.nl))
- `device_type`: The type of the device. See the [device types](device-types/index.md) section for more information.
- `calculation_strategy`: The calculation strategy to use. See the [strategies](../strategies/index.md) section for more information.
- `measure_method`: The method used to measure the device. This can be `manual` or `script`.
- `measure_device`: The device used to measure the power usage. (For example `Shelly PM Gen 3`)
- `created_at`: The date when the profile was created. (ISO 8601 format, i.e. `2023-06-19T08:02:31`)
- `author`: The author of the profile.

You can use `aliases` to define alternative model names, which will be used during discovery.
This can be helpful when same model is reported differently depending on the integration. For example, the same light bulb could be reported differently by the Hue integration compared to the deCONZ integration.

By default Powercalc discovers on a "per entity" basis.
This can cause issues when a device has multiple entities, causing multiple discoveries for the same device.
When a profile does not have to be bound to a specific entity (light, switch etc.), you can set `discovery_by` to `device`.
This will cause Powercalc to discover on a "per device" basis, which is more reliable.
This setting is recommended for device types which map to `sensor` domain entities, these are: `network`, `power_meter` and `generic_iot`.

## Sub profiles

Some profiles might have multiple profiles. This is useful when a device has different power consumption based on the state of the device.
See [sub profiles](sub-profiles.md) for more information.
