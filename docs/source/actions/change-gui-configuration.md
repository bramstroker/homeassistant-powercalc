# Change GUI Configuration

To change the configuration options for all Powercalc GUI config entries at once you can utilize the action `powercalc.change_gui_config`.
You can use it to change the configuration for the following options

- create_energy_sensor
- create_utility_meters
- ignore_unavailable_state
- energy_integration_method

You can call this action from the GUI (`Developer tools` -> `Actions`).
For example to set `create_utility_meters` to yes for all powercalc GUI configurations:

## Example

```yaml
action: powercalc.change_gui_config
data:
  field: create_utility_meters
  value: 1
```
