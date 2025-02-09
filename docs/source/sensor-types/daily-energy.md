# Daily fixed energy

Sometimes you want to keep track of energy usage of individual devices which are not managed by Home Assistant.
When you know the energy consumption in kWh or W powercalc can make it possible to create an energy sensor (which can also be used in the energy dashboard).
This can be helpful for devices which are always on and have a relatively fixed power draw. For example an IP camera, intercom, Google nest, Alexa, network switches etc.

## Configuration options

| Name                | Type    | Requirement  | Default  | Description                                                                                                          |
| ------------------- | ------- | ------------ | -------- | -------------------------------------------------------------------------------------------------------------------- |
| value               | float   | **Required** |          | Value either in watts or kWh. Can also be a [template](https://www.home-assistant.io/docs/configuration/templating/) |
| unit_of_measurement | string  | **Optional** | kWh      | `kWh` or `W`                                                                                                         |
| on_time             | period  | **Optional** | 24:00:00 | How long the device is on per day. Only applies when `unit_of_measurement` is set to `W`. Format `HH:MM:SS`          |
| update_frequency    | integer | **Optional** | 1800     | Seconds between each increase in kWh                                                                                 |

## Examples

This will add 0.05 kWh per day to the energy sensor called "IP camera upstairs"

```yaml
powercalc:
  sensors:
    - name: IP camera upstairs
      daily_fixed_energy:
        value: 0.05
```

Or define in watts, with an optional on time (which is 24 hour a day by default).

```yaml
powercalc:
  sensors:
    - name: Intercom
      daily_fixed_energy:
        value: 21
        unit_of_measurement: W
        on_time: 12:00:00
```

This will simulate the device using 21 watts for 12 hours a day. The energy sensor will increase by 0.252 kWh a day.

!!! note

    When you use `on_time` no power sensor (W) will be created, but only an energy sensor (kWh) will be available.

## Actions

### Resetting sensor

To reset the energy sensor to zero use the `powercalc.reset_energy` action.

```yaml
action: powercalc.reset_energy
target:
  entity_id: sensor.my_energy
```

### Increasing sensor

To increase the sensor with a given value use the [`powercalc.increase_daily_energy` action](../actions/increase-daily-energy.md).
