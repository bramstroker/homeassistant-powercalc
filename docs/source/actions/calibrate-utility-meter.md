# Calibrate Utility Meter

Use this action to set a utility meter to a forced new value.

## Example

```yaml
action: powercalc.calibrate_utility_meter
data:
  value: "20"
target:
    entity_id: sensor.washing_machine_energy_yearly
```
