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
