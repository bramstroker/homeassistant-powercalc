# Smart switch

Used for smart plugs / smart switches which can toggle a connected device on or off.

## JSON

Below are different examples of how to configure a smart switch device in the library.
Depending on the capabilities of the smart switch, select the appropriate configuration.

## Smart switch without built-in powermeter

The profile will provide self-usage measurements for the smart switch itself, and will ask the user to provide the power consumption of the connected device.

```json
{
  "standby_power": 0.3,
  "standby_power_on": 0.7,
  "device_type": "smart_switch",
  "calculation_strategy": "fixed"
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the [model structure](../structure.md)

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
  "standby_power": 0.3,
  "standby_power_on": 0.7,
  "sensor_config": {
    "power_sensor_naming": "{} Device Power",
    "energy_sensor_naming": "{} Device Energy"
  },
  "device_type": "smart_switch",
  "calculation_strategy": "fixed",
  "only_self_usage": true
}
```

Following the example above, the following power values will be calculated:
- ON: 0.7W
- OFF: 0.3W

## Smart switch with multiple relays

Some smart switches have multiple relays, each controlling a different device.
To integrate this you can utilize the [multi_switch](../../strategies/multi-switch.md) calculation strategy.

Examples of this type of smart switch are:

- TP-Link Kasa HS300
- Shelly 2.5

```json
{
  "calculation_strategy": "multi_switch",
  "discovery_by": "device",
  "standby_power": 0.25,
  "multi_switch_config": {
    "power": 0.8
  },
  "sensor_config": {
    "power_sensor_naming": "{} Device Power",
    "energy_sensor_naming": "{} Device Energy"
  },
  "only_self_usage": true
}
```

This configuration will set the self usage of the switch to 0.25W, for each relay which is activated 0.8W will be added.
So assuming switch with 4 relays, and 2 are activated the following power values will be calculated:
2 * 0.8 + 0.25 = 1.85W

## Measure

Start by disconnecting the device from the smart switch, as we need to measure the power consumption of the smart switch itself, not the device it controls.
Next, plug the smart switch into the power meter (smart plug) you will be using for the measurement.

The ability to measure the smart switch's standby power depends on the smart plug you're using. Some plugs may not be able to measure very low values.

The Zhurui PR10 smart plug is a good option, as it can measure power as low as 0.1W.

Alternatively, you can try another smart plug, but you might need to add a dummy load to the smart switch to get an accurate measurement.
When using a smart plug, you can use the [measure tool](../../contributing/measure.md) and select the `average` mode for 1 minute to get a reading.

Now, you’re ready to measure the smart switch's power consumption in both the `ON` and `OFF` states.

- Turn the switch ON in HA
- Record the power reading
- Turn the switch OFF in HA
- Record the power reading

Choose the appropriate example JSON for your situation and replace the values with the ones you've measured.
