# Energy sensors

An energy sensor provides a measurement in kWh, which is a measurement of power usage over time.
For example when you have a device of 1000 Watt running for 1 hour you have used 1000 Wh which equals to 1 kWh.
Powercalc can automatically create energy sensors for your virtual power meters. It uses the Riemann Sum helper for that.

By default energy sensors are created for all your powercalc power meters, but if you don't like that you can disable that with the `create_energy_sensors` option.

```yaml
powercalc:
  create_energy_sensors: false
```

You can also set this option per sensor in YAML or when you use the GUI you can toggle this in the options.

## Standby energy

For virtual power sensors, you can create an additional energy sensor which tracks only the
standby portion of the calculated power. Enable **Create standby energy sensor** in the GUI,
or set `create_standby_energy_sensor` in YAML:

```yaml
powercalc:
  sensors:
    - entity_id: light.example
      create_standby_energy_sensor: true
```

The sensor is disabled by default and is named `<device> standby energy`. It uses the same
integration method, precision, unit prefix, and update interval as the regular energy sensor.
The regular energy sensor still includes standby consumption; the standby sensor is a separate
breakdown and is excluded from Powercalc group energy totals to prevent double counting.

## Resetting energy sensor

Powercalc provides an action [`powercalc.reset_energy`](../actions/reset-energy.md) which you can call to reset energy sensors to 0 kWh.
You can call this action from the GUI (`Developer tools` -> `Actions`) or use this in automations.

## Calibrating energy sensor

Powercalc provides an action [`powercalc.calibrate_energy`](../actions/calibrate-energy.md) which you can call to set an energy sensor to a forced new value.
This can be useful if somehow the energy sensor has an erroneous value.

You can call this action from the GUI (`Developer tools` -> `Actions`).
