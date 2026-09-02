# Humidifier

Humidifiers are represented by a Home Assistant `humidifier` entity.

Profiles can use a fixed calculation strategy for devices whose active power consumption is constant.

## JSON

```json
{
  "calculation_strategy": "fixed",
  "device_type": "humidifier",
  "fixed_config": {
    "power": 25
  },
  "standby_power": 0.4
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the
    [model structure](../structure.md).
