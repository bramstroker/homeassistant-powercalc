# Calibrate Cost

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.calibrate_cost)

Use this action to set a cost sensor to a forced new monetary value.
After calibration, Powercalc uses the current source energy value as the new baseline so already consumed energy is not counted again.

## Example

```yaml
action: powercalc.calibrate_cost
data:
  value: "20"
target:
  entity_id: sensor.washing_machine_cost
```
