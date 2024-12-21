# Smart switch

Below are different examples of how to configure a smart switch device in the library.
Depending on the capabilities of the smart switch, select the appropriate configuration.

## Smart switch without built-in powermeter

The profile will provide self-usage measurements for the smart switch itself, and will ask the user to provide the power consumption of the connected device.

```json
{
  "measure_method": "manual",
  "measure_device": "Some device",
  "name": "Some smart switch",
  "standby_power": 0.3,
  "standby_power_on": 0.7,
  "device_type": "smart_switch",
  "calculation_strategy": "fixed"
}
```

When this profile is discovered, the user will be asked to provide the power consumption of the connected device.
Assuming the user provides a value of 50W the following power values will be calculated:
- ON: 50.7W
- OFF: 0.3W

!!! note

    During the configuration flow the user als has the option to toggle `self_usage_included` on or off.
    When toggled on the power when ON will be 50W instead of 50.7W, in the example above.

## Smart switch with built-in powermeter

!!! note

    In this scenario Powercalc will only provide the self-usage measurements for the smart switch itself.
    As the smart switch itself already measures the connected appliance.

Note the sensor_naming configuration which will make sure the entities are named different than the power entities already provided, so they don't conflict.

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
    "power": 0.7
  }
}
```

Following the example above, the following power values will be calculated:
- ON: 0.7W
- OFF: 0.3W

## Measure

Start by disconnecting the device from the smart switch, as we need to measure the power consumption of the smart switch itself, not the device it controls.
Next, plug the smart switch into the power meter (smart plug) you will be using for the measurement.

The ability to measure the smart switch's standby power depends on the smart plug you're using. Some plugs may not be able to measure very low values.

The Zhurui PR10 smart plug is a good option, as it can measure power as low as 0.1W.

Alternatively, you can try another smart plug, but you might need to add a dummy load to the smart switch to get an accurate measurement.
When using a smart plug, you can use the [measure utility](../../contributing/measure.md) and select the `average` mode for 1 minute to get a reading.

Now, you’re ready to measure the smart switch's power consumption in both the `ON` and `OFF` states.

- Turn the switch ON in HA
- Record the power reading
- Turn the switch OFF in HA
- Record the power reading

Choose the appropriate example JSON for your situation and replace the values with the ones you've measured.
