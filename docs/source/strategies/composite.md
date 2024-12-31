# Composite

The composite strategy allows you to create power sensor which contains of multiple strategies.
For each strategy you can setup conditions which indicate when the strategy should be applied.
So for example you could use the `fixed` strategy when a certain condition applies, and the `linear` when another condition applies.
For the conditions the same engine is used as in HA automations and scripts. See <https://www.home-assistant.io/docs/scripts/conditions/>.
All conditions are supported, except for the `time` and `trigger` condition.

Currently this is a YAML only feature

## Modes

The composite strategy supports the following modes:

- `stop_at_first`: The first strategy that matches the condition will be used. This is the default mode.
- `sum_all`: All strategies that match the condition will be used and the power will be summed.

## Usage

Let's start with a simple example:

```yaml
powercalc:
  sensors:
    - entity_id: switch.heater
      composite:  # This indicates the composite strategy is used
        - condition:
            condition: state
            entity_id: select.heater_mode
            state: high
          fixed:
            power: 1000
        - fixed:
            power: 500
```

This will create a power sensor `sensor.heater_power`. Whenever the `select.heater_mode` is high the power sensor will be 1000 and in all other cases 500.

!!! note

    Strategies will be checked in the order in which they were registered. Until the condition matches.

You can mix/match strategies and also use composed conditions using `OR` and `AND`.
For example:

```yaml
powercalc:
  sensors:
    - entity_id: light.test
      composite:
        # First strategy (fixed) using nested AND and OR conditions
        - condition:
            condition: and
            conditions:
              - condition: state
                entity_id: binary_sensor.test
                state: on
              - condition: or
                conditions:
                  - condition: numeric_state
                    entity_id: sensor.test
                    above: 20
                    below: 40
                  - condition: template
                    value_template: "{{ is_state('sensor.test2', 'test') }}"
          fixed:
            power: 10
        # Second strategy (linear)
        - condition:
            condition: state
            entity_id: binary_sensor.test
            state: off
          linear:
            min_power: 20
            max_power: 40
```

When no condition matches for any strategy the power sensor will become `unavailable` or when the `light.test` is OFF powercalc will look at the `standby_power`
You can omit `condition` on the last register strategy so that will always be used as a fallback.

!!! warning

    Don't omit `condition` field on any strategy other than the last as that will cause the strategy chain to stop at that one.

## Sum all mode

When using the `sum_all` mode all strategies that match the condition will be used and the power will be summed.

```yaml
powercalc:
  sensors:
    - entity_id: humidifier.test
      composite:
        mode: sum_all
        strategies:
          - condition:
              condition: state
              entity_id: input_boolean.motor1
              state: on
            fixed:
              power: 1000
          - fixed:
              power: 500
```

In this example the power sensor will be 1500 when `input_boolean.motor1` is on and 500 when it is off.

!!! note

    When using the `sum_all` mode the power sensor will become `0` when no strategy matches the condition.

## Usage in library profiles

You can also use the composite strategy in library profiles. For example:

```json
{
  "calculation_strategy": "composite",
  "composite_config": [
    {
      "condition": {
        "condition": "numeric_state",
        "above": 17
      },
      "fixed": {
        "power": 0.82
      }
    },
    {
      "fixed": {
        "power": 0.52
      }
    }
  ]
}
```
