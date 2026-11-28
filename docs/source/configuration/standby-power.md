# Standby power

When you defined a virtual power sensor and the referenced entity is OFF, Powercalc will consider the appliance standby and use the `standby_power` option to determine it's power.
The following states are considered off for powercalc:

- off
- not_home
- standby
- unavailable

Given the following example:

```yaml
powercalc:
  sensors:
    - entity_id: light.some_light
      fixed:
        power: 50
      standby_power: 2
```

When the light is `ON` power will be 50, when the light is `OFF` power will be 2.

Passing templates as the `standby_power` value is also supported for entities created with YAML.

## Controller draw while on

Some devices keep drawing power for their own controller even while their load is running: a smart plug, a dimmer, a router or a UPS. Profiles can declare that with `standby_power_on`, and manually configured sensors can now use the same option.

`standby_power_on` is **added on top of** the power of the running load. It does not replace `standby_power`. In the example below the plug draws 12.4 W for its own electronics while the connected load runs at 48 W, so the sensor reports 60.4 W while the switch is on and 12.4 W while it is off.

```yaml
powercalc:
  sensors:
    - entity_id: switch.tasmota_plug
      standby_power: 12.4
      standby_power_on: 12.4
      fixed:
        power: 48
```

Do not set both `fixed.power` and `standby_power_on` to the same total: with `fixed.power: 12.4` and `standby_power_on: 12.4` the sensor would report 24.8 W. `fixed.power` is the load, `standby_power_on` is the controller overhead.

The controller draw is also part of the [standby group](../sensor-types/group/standby.md), because that group tracks phantom consumption of devices that are currently on.

## Sleep power

This setting comes in handy when a device enters a sleep mode after X amount of time which changes the power consumption.

You'll need to define both `power` and `delay`.

```yaml
powercalc:
  sensors:
    - entity_id: media_player.smart_speaker
      fixed:
        power: 4
      standby_power: 1
      sleep_power:
        power: 0.3
        delay: 200
```

In the above scenario power will be 4 when the media player is on and/or actively playing.
When the media player turns off the power will change to 1, then after 200 seconds the sleep mode will get activated and power will change to 0.3.
