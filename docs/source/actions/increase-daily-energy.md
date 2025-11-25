# Increase daily energy

To increase the sensor with a given value use the `powercalc.increase_daily_energy` action.

!!! tip

    This can be useful in automations where you want to increase the energy sensor when a certain event occurs (using triggers).
    For example use a NFC tag to register a dishwasher cycle and increase the sensor with the known kWh for one cycle.
    Or measure the kWh once for certain programs of your smart washing machine, and use the program states in automation to increase the energy sensor.

## Example

```yaml
action: powercalc.increase_daily_energy
data:
  value: 100
target:
  entity_id: sensor.my_energy
```

This will increase the energy sensor with 100 Kwh or 100 W when you have set `unit_of_measurement` to `W`
