# Reset Energy

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.reset_energy)

Reset an energy sensor to 0 kWh

## Example

```yaml
action: powercalc.reset_energy
target:
  entity_id: sensor.washing_machine_energy
```
