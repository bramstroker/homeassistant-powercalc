# Smart dimmer

Below are some examples of how to configure a smart switch device in the library.

## Smart switch with relay

```json
{
  "measure_method": "manual",
  "measure_device": "Some device",
  "name": "Some smart switch",
  "standby_power": 0.3,
  "standby_power_on": 0.7,
  "sensor_config": {
    "power_sensor_naming": "{} Device Power",
    "energy_sensor_naming": "{} Device Energy"
  },
  "device_type": "smart_switch",
  "calculation_strategy": "fixed"
}
```

When this profile is discovered, the user will be asked to provide the power consumption of the connected device.
Assuming the user provides a value of 50W the following power values will be calculated:
- ON: 50.7W
- OFF: 0.3W

... note::
    During the configuration flow the user als has the option to toggle `self_usage_included` on or off.
    When toggled on the power when ON will be 50W instead of 50.7W, in the example above.

## Smart switch without relay

Smart switches that can only measure power consumption, but don't have a relay to toggle the power, can be configured as follows:

```json
{
  "measure_method": "manual",
  "measure_device": "Some device",
  "name": "Some smart switch",
  "standby_power": 0.3,
  "sensor_config": {
    "power_sensor_naming": "{} Device Power",
    "energy_sensor_naming": "{} Device Energy"
  },
  "device_type": "smart_switch",
  "calculation_strategy": "fixed",
  "fixed_config": {
    "power": 0.8
  }
}
```

In this scenario, the user will NOT be asked to provide the power consumption of the connected device.

Following the example above, the following power values will be calculated:
- ON: 0.8W
- OFF: 0.3W
