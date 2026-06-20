# Reload

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.reload)

Powercalc provided a reload action which can be used to reload sensors when you modify the YAML configuration.
This action is useful when you want to reload the sensors without restarting the HA instance.

This action can also be called from `Developer Tools` -> `YAML` section.
When HA provides a list of integrations which support YAML reloading, you can find the `powercalc` integration in the list.

## Example

```yaml
action: powercalc.reload
data: {}
```

## Working

When triggering this action Powercalc will do the following:

- Reload the YAML configuration.
- Update the global configuration.
- Reinitialize the sensors with the new configuration.
- Reload all Powercalc config entries (GUI configuration)
