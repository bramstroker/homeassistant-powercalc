# Smart dimmer

Smart dimmers are devices that can control the brightness of a light. They are often used in combination with LED lights.

## JSON

Use the following model.json to configure a smart dimmer device type.

## Smart dimmer without built-in powermeter

The profile will provide self-usage measurements for the smart dimmer itself, and will ask the user to provide the power consumption of the connected light.

```json
{
  "standby_power": 0.3,
  "standby_power_on": 0.5,
  "device_type": "smart_dimmer",
  "calculation_strategy": "linear"
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the [model structure](../structure.md)

For smart dimmer devices the user can additionally supply [linear](../../strategies/linear.md) configuration to define the power consumption of the connected light.
When not supplied, the power consumption is assumed to be 0.5W when the light is on and 0.3W when the light is off.

To do this in YAML use the following configuration:

```yaml
powercalc:
  sensors:
    - entity_id: light.some_light
      manufacturer: xx # reference to the library manufacturer
      model: xx # reference to the library model
      linear:
        min_power: 2
        max_power: 20
```

When using GUI configuration flow (either discovery or manual), the user will be able to define the linear configuration for the light.

A profile can provide a normalized dimming curve while still asking the user for the connected light's minimum and maximum power:

```json
{
  "device_type": "smart_dimmer",
  "calculation_strategy": "linear",
  "min_version": "v1.26.0",
  "linear_config": {
    "power_curve": [
      "0.00 -> 0.00",
      "0.50 -> 0.20",
      "1.00 -> 1.00"
    ]
  }
}
```

Both sides of every point use a normalized 0–1 scale. Powercalc interpolates the curve and scales its output to the power range supplied by the user.

!!! important

    A profile using `power_curve` must set `min_version` to `v1.26.0` or higher, the release that added support for it. Older Powercalc versions do not recognize the option and would silently fall back to a straight line between the user's minimum and maximum power, reporting plausible but wrong numbers. With `min_version` set, those versions skip the profile instead.

## Smart dimmer with built-in powermeter

When the dimmer already has a built-in powermeter, the following configuration can be used:

```json
{
  "standby_power": 0.3,
  "device_type": "smart_dimmer",
  "calculation_strategy": "linear",
  "only_self_usage": true
}
```

The `only_self_usage` flag is set to true to indicate that the power consumption of the connected light is already measured by the dimmer itself.
In this scenario the user also won't be asked to provide the power consumption of the connected light during the configuration wizard.
