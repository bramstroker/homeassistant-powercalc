# Smart dimmer

Smart dimmers are devices that can control the brightness of a light. They are often used in combination with LED lights.

## JSON

Use the following model.json to configure a smart dimmer device type.

```json
{
  "name": "Some smart dimmer",
  "standby_power": 0.3,
  "standby_power_on": 0.5,
  "device_type": "smart_dimmer",
  "calculation_strategy": "linear"
}
```

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
