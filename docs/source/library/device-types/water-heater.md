# Water heater

Water heaters are represented by a Home Assistant `water_heater` entity.

Use a fixed or composite calculation strategy when consumption depends on the operation mode or other entity attributes.

## JSON

```json
{
  "calculation_strategy": "fixed",
  "device_type": "water_heater",
  "fixed_config": {
    "states_power": {
      "electric": 2000,
      "heat_pump": 500
    }
  },
  "standby_power": 1.0
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the
    [model structure](../structure.md).
