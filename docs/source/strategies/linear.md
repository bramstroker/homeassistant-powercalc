# Linear

Supported domains: `light`, `fan`, `media_player`

The linear mode can be used for dimmable devices which don't have a lookup table available.
You need to supply the min and max power draw yourself, by either looking at the datasheet or measuring yourself with a smart plug / power meter.
Power consumpion is calculated by ratio. So when you have your fan running at 50% speed and define watt range 2 - 6, than the estimated consumption will be 4 watt.

You can setup sensors both with YAML or GUI.
When you use the GUI select `linear` in the calculation_strategy dropdown.

## Configuration options

| Name        | Type   | Requirement  | Description                                                                                                                                           |
| ----------- | ------ | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| attribute   | string | **Optional** | State attribute to use for the linear range. When not supplied will be `brightness` for lights, `percentage` for fans and `volume` for media players. |
| min_power   | float  | **Optional** | Power usage for lowest brightness level                                                                                                               |
| max_power   | float  | **Optional** | Power usage for highest brightness level                                                                                                              |
| calibrate   | string | **Optional** | Calibration values                                                                                                                                    |
| gamma_curve | float  | **Optional** | Apply a gamma correction, for example 2.8                                                                                                             |

**Example configuration**

```yaml
powercalc:
  sensors:
    - entity_id: light.livingroom_floorlamp
      linear:
        min_power: 0.5
        max_power: 8
```

!!! note

    defining only `min_power` and `max_power` is only allowed for light and fan entities, when you are using another entity (for example a `sensor` or `input_number`) you must use the calibrate mode.

## Advanced precision calibration

With the `calibrate` option you can supply more than one power value for multiple brightness/percentage levels.
This allows for a more accurate estimation because not all lights are straight linear.

Also you can use this calibration table for other entities than lights and fans, to supply the state values and matching power values.

```yaml
powercalc:
  sensors:
    - entity_id: light.livingroom_floorlamp
      linear:
        calibrate:
          - 1 -> 0.3
          - 10 -> 1.25
          - 50 -> 3.50
          - 100 -> 6.8
          - 255 -> 15.3
```

When setting up with the GUI you'll need to supply following format:

```
1: 0.3
10: 1.25
50: 3.50
100: 6.8
255: 15.3
```

!!! note

    For lights the supplied values must be in brightness range 1-255, when you select 1 in lovelace UI slider this is actually brightness level 3.
    For fan speeds the range is 1-100 (percentage)

Configuration with a sensor (`sensor.heater_modulation`) which supplies a percentage value (1-100):

```yaml
powercalc:
  sensors:
    - entity_id: sensor.heater_modulation
      name: Heater
      linear:
        calibrate:
          - 1 -> 200
          - 100 -> 1650
```

You could also use this to setup a power profile for your robot vacuum cleaner, which only consumes power when it is docked into the charching port. You need to use this in conjunction with the `calculation_enabled_condition` to only activate the power calculation when the device is docked.

```yaml
powercalc:
  sensors:
    - entity_id: vacuum.my_robot_cleaner
      calculation_enabled_condition: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}"
      linear:
        attribute: battery_level
        calibrate:
          - 1 -> 20
          - 79 -> 20
          - 80 -> 15
          - 99 -> 8
          - 100 -> 1.5
```
