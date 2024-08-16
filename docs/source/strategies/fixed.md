# Fixed

When you have an appliance which only can be set on and off you can use this mode.
You need to supply a single watt value in the configuration which will be used when the device is ON
Also we provide an option to define power values for certain entity states.

You can setup sensors both with YAML or GUI.
When you use the GUI select `fixed` in the calculation_strategy dropdown.

## Configuration options

| Name         | Type  | Requirement  | Description                                                                     |
| ------------ | ----- | ------------ | ------------------------------------------------------------------------------- |
| power        | float | **Optional** | Power usage when the appliance is turned on (in watt). Can also be a [template] |
| states_power | dict  | **Optional** | Power usage per entity state. Values can also be a [template]                   |

**Simplest example**

```yaml
powercalc:
  sensors:
    - entity_id: light.nondimmabled_bulb
      fixed:
        power: 20
```

**Using a template for the power value**

```yaml
powercalc:
  sensors:
    - entity_id: light.bathroom
      fixed:
        power: "{{states('input_number.bathroom_watts')}}"
```

When you don't have a source entity or helper (ex. `input_boolean`) to bind on and you just want the power sensor to reflect the template value you can use `sensor.dummy` as the entity_id

```yaml
powercalc:
  sensors:
    - entity_id: sensor.dummy
      name: Bathroom lights
      fixed:
        power: "{{states('input_number.bathroom_watts')}}"
```

**Example with standby power**

```yaml
powercalc:
  sensors:
    - entity_id: switch.test
      fixed:
        power: 5
      standby_power: 0.5
```

## Power per state

The `states_power` setting allows you to specify a power per entity state. This can be useful for example on Sonos devices which have a different power consumption in different states.

```yaml
powercalc:
  sensors:
    - entity_id: media_player.sonos_living
      fixed:
        states_power:
          playing: 8.3
          paused: 2.25
          idle: 1.5
```

!!! warning

    Some states you cannot use as they are considered "off" for powercalc. In this case you'll need to use `standby_power`.
    The states which this applies to are `off`, `not_home`, `standby` and `unavailable`.

You can also use state attributes. Use the `|` delimiter to seperate the attribute and value. Here is en example:

```yaml
powercalc:
  sensors:
    - entity_id: media_player.sonos_living
      fixed:
        power: 12
        states_power:
          media_content_id|Spotify: 5
          media_content_id|Youtube: 10
```

When no match is found in `states_power` lookup than the configured `power` will be considered.

[template]: https://www.home-assistant.io/docs/configuration/templating/
