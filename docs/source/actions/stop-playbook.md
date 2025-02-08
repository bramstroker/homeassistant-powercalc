# Stop Playbook

This service is used to stop a running playbook.
It only works with virtual power sensors having the [playbook strategy](../strategies/playbook.md) configured.

## Example

```yaml
action: powercalc.stop_playbook
data:
  playbook_id: program1
target:
  entity_id: sensor.waching_machine_power
```
