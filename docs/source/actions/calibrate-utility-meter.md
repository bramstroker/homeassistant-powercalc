# Calibrate Utility Meter

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.calibrate_utility_meter)

Use this action to set a utility meter to a forced new value.

## Example

```yaml
action: powercalc.calibrate_utility_meter
data:
  value: "20"
target:
    entity_id: sensor.washing_machine_energy_yearly
```
