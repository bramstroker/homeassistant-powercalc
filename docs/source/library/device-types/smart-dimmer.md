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

## Smart dimmer with built-in powermeter

When the dimmer already has a built-in powermeter, the following configuration can be used:

```json
{
  "standby_power": 0.3,
  "sensor_config": {
    "power_sensor_naming": "{} Device Power",
    "energy_sensor_naming": "{} Device Energy"
  },
  "device_type": "smart_dimmer",
  "calculation_strategy": "linear",
  "only_self_usage": true
}
```

The `only_self_usage` flag is set to true to indicate that the power consumption of the connected light is already measured by the dimmer itself.
In this scenario the user also won't be asked to provide the power consumption of the connected light during the configuration wizard.
