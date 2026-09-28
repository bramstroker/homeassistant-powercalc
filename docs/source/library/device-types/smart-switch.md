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

    During the configuration flow the user also has the option to toggle `self_usage_included` on or off.
    When toggled on the power when ON will be 50W instead of 50.7W, in the example above.

## Smart switch with built-in powermeter

!!! note

    In this scenario Powercalc will only provide the self-usage measurements for the smart switch itself.
    As the smart switch itself already measures the connected appliance.

```json
{
  "standby_power": 0.3,
  "standby_power_on": 0.7,
  "device_type": "smart_switch",
  "calculation_strategy": "fixed",
  "only_self_usage": true
}
```

Because of `only_self_usage` the sensors are named `{} Device Power` and `{} Device Energy` instead of `{} power` and `{} energy`,
so they don't conflict with the power entities the switch already provides. This naming is applied by Powercalc itself,
a profile must never set `power_sensor_naming` or `energy_sensor_naming`.

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
  "only_self_usage": true
}
```

This configuration will set the self usage of the switch to 0.25W, for each relay which is activated 0.8W will be added.
So assuming switch with 4 relays, and 2 are activated the following power values will be calculated:
2 * 0.8 + 0.25 = 1.85W

## Measure

Select **Smart switch** in the [Measure app](../../contributing/measure/index.md). The automated runner measures the switch's own power use, not an appliance connected to its output. **Disconnect every load from every relay output** and disable automations that could switch a relay during the run. The ready screen asks you to confirm this before PowerCalc operates any relay.

Connect a precise external power meter upstream of the switch. Its resolution must be good enough to distinguish the switch's small off and on power draws. The switch's built-in power sensor cannot measure its own self consumption. When the external meter cannot resolve these low readings, a calibrated resistive dummy load may be connected **in parallel with the switch**, upstream of the relay outputs. Never connect the dummy load to a switched output. Follow the [low-power measurement guide](../../contributing/measure/low-power-measurements.md).

Select one relay for a fixed profile, or all relays on the same Home Assistant device for a `multi_switch` profile. State whether the switch has built-in power monitoring; this sets `device_specs.power_monitoring`. PowerCalc repeats the off and on measurements, checks their consistency, saves the individual readings, and restores the original relay states when it finishes or is cancelled.

For multiple relays, PowerCalc measures an all-off baseline, each relay on separately, and all relays on. The relays must have sufficiently similar self-consumption increments for the shared `multi_switch_config.power` value. Multi-relay profiles use `only_self_usage: true` whether or not the device has built-in power monitoring. Model the appliances connected to its outputs separately. For a single relay without built-in power monitoring, the fixed profile can ask the user for the connected appliance's power as described above.
