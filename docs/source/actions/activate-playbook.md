# Activate Playbook

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.activate_playbook)

This service is used to start executing a playbook.
It only works with virtual power sensors having the [playbook strategy](../strategies/playbook.md) configured.

## Example

```yaml
action: powercalc.activate_playbook
data:
  playbook_id: program1
target:
  entity_id: sensor.waching_machine_power
```
