# Reset Cost

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.reset_cost)

Reset a cost sensor to 0.
After reset, Powercalc uses the current source energy value as the new baseline so already consumed energy is not counted again.

## Example

```yaml
action: powercalc.reset_cost
target:
  entity_id: sensor.washing_machine_cost
```
