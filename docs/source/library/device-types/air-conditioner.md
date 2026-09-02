# Air conditioner

Air conditioners are represented by a Home Assistant `climate` entity.

Use a fixed or composite calculation strategy when consumption depends on the HVAC mode or other entity attributes.

## JSON

```json
{
  "calculation_strategy": "fixed",
  "device_type": "air_conditioner",
  "fixed_config": {
    "states_power": {
      "cool": 750,
      "fan_only": 35
    }
  },
  "standby_power": 1.2
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the
    [model structure](../structure.md).
