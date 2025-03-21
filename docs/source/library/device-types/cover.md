# Cover

Blinds, awnings, shutters, curtains etc.

## JSON

```json
{
  "standby_power": 0.2,
  "standby_power_on": 0.2,
  "device_type": "cover",
  "calculation_strategy": "fixed",
  "fixed_config": {
    "states_power": {
      "opening": 150,
      "closing": 150
    }
  }
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the [model structure](../structure.md)

This profile is for a cover device that uses 150W when opening or closing. The standby power is 0.2W.
