# Calibrate Energy

Use this action to set an energy sensor to a forced new value.
This can be useful if somehow the energy sensor has an erroneous value.

!!! note
    Groups which this energy sensor is part of will also be increased with the new value.

## Example

```yaml
action: powercalc.calibrate_energy
data:
  value: "20"
target:
    entity_id: sensor.washing_machine_energy
```
