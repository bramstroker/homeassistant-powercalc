# Calibrate Energy

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.calibrate_energy)

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
