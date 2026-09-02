# Air purifier

Air purifiers are represented by a Home Assistant `fan` entity.

Use the linear calculation strategy when power consumption follows the configured fan percentage.

## JSON

```json
{
  "calculation_strategy": "linear",
  "device_type": "air_purifier",
  "linear_config": {
    "calibrate": [
      "0 -> 2.0",
      "50 -> 12.0",
      "100 -> 35.0"
    ]
  },
  "standby_power": 0.5
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the
    [model structure](../structure.md).
