# Multiply Factor

This feature allows you to multiply the calculated power.

A library profile can provide a default multiplier, including one based on a custom field such as the number of panels.
An explicit `multiply_factor` in your sensor configuration overrides the profile's value.
Standby power, including the controller's `standby_power_on`, is added once unless you enable `multiply_factor_standby`.

This can be useful in the following use cases:

- You have a bunch of similar lights which you control as a group and want a single power sensor.
- You are using a LED strip from the LUT models, but you have extended or shortened it.

Let's assume you have a combination of 4 GU10 spots in your ceiling in a light group `light.livingroom_spots`

```yaml
powercalc:
  sensors:
    - entity_id: light.livingroom_spots
      multiply_factor: 4
```

This will add the power sensor `sensor.livingroom_spots_power` and the measured power will be multiplied by 4, as the original measurements are for 1 spot.

By default the multiply factor will **NOT** be applied to the standby power, you can set the `multiply_factor_standby` to do this.

```yaml
powercalc:
  sensors:
    - entity_id: light.livingroom_spots
      multiply_factor: 4
      multiply_factor_standby: true
```

!!! tip

    A `multiply_factor` lower than 1 will decrease the power. For example 0.5 will half the power.
