# Multi Switch

:material-tag-outline: 1.14 or higher

The multi switch strategy allows you to combine the self usage of multiple switches into a single entity.
This can be used for example to make a profile for Tp-Link HS300 power strip.

You can setup sensors both with YAML or GUI.
When you use the GUI select `multi_switch` in the calculation_strategy dropdown.

## Configuration options

| Name      | Type    | Requirement  | Default | Description                                      |
| --------- | ------- | ------------ | ------- | ------------------------------------------------ |
| entities  | list    | **Required** |         | Provide a list of the individual switch entities |
| power     | decimal | **Required** |         | Power for one outlet when it is switched on      |
| power_off | decimal | **Required** |         | Power for one outlet when it is switched off     |

```yaml
powercalc:
  sensors:
    - name: "My outlet self usage"
      multi_switch:
        entities:
          - switch.outlet_1
          - switch.outlet_2
          - switch.outlet_3
        power_off: 0.25
        power: 0.5
```

In this example, when all the switches are turned on, the power usage will be 0.5W * 3 = 1.5W
When only `switch.outlet_1` is turned on, the power usage will be 0.5W + 0.25W + 0.25W = 1W
