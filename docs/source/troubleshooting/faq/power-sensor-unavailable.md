# What to do when power sensor is unavailable?

By default, Powercalc sensors will become `unavailable` when the source entity is `unavailable` or `unknown`.

A Powercalc sensor can also become `unavailable` if there is an error in the strategy handling or the powercalc profile.

## Source entity unavailable
When the source entity is unavailable, you can control the behavior in two ways:

### Ignore unavailable state
By using the `ignore_unavailable_state` option, you can keep the Powercalc sensor available, even when the source entity is unavailable.
This is especially useful for group sensors, as it ensures the group remains available and continues to calculate the total power based on the remaining members.

### Custom unavailable power
Alternatively, you can provide a custom power value to be used when the source entity is unavailable by using the `unavailable_power` option.
This allows you to specify a fixed amount of power (in Watts) that should be recorded for the device when its state cannot be determined.

## Internal errors
If the source entity is available, but the Powercalc sensor is still `unavailable`, this might be caused by an error in the calculation strategy.

### Strategy handling errors
This can happen when a misbehaving integration reports a wrong color mode or other state information that Powercalc cannot process.
Check the [Home Assistant logs](../debug-logging.md) for any error messages related to `powercalc`.

### Profile errors
There might be an error in the Powercalc profile for your specific device.
If you suspect an error in the profile, please check the logs and report the issue on the GitHub repository.

## Configuration
Both `ignore_unavailable_state` and `unavailable_power` can be configured via the UI (in the "Advanced options" section of the configuration flow) or via YAML.

#### YAML example
```yaml
powercalc:
  sensors:
    - entity_id: light.my_light
      ignore_unavailable_state: true
      unavailable_power: 0.5
```
