# Sensor Naming

This page described how entities are named by default in Powercalc and the options to change that behaviour.

## Default naming convention

Let's assume you have a source sensor `light.patio` with name "Patio".
Powercalc will create the following sensors by default.

- sensor.patio_power (Patio power)
- sensor.patio_energy (Patio energy)

!!! note

    Utility meters will use the energy name as a base and suffix with `_daily`, `_weekly`, `_monthly`

## Change suffixes

To change the default suffixes `_power` and `_energy` you can use the `power_sensor_naming` and `energy_sensor_naming` options.
The following configuration:

```yaml
powercalc:
  energy_sensor_naming: "{} kWh consumed"
```

will create following sensors:

- sensor.patio_power (Patio power)
- sensor.patio_kwh_consumed (Patio kWh consumed)

## Friendly naming

This option allows you to separately change only the name (shown in GUI), it will not have effect on the entity id

```yaml
powercalc:
  energy_sensor_naming: "{} kwh"
  energy_sensor_friendly_naming: "{} Energy consumed
```

will create following sensors:

- sensor.patio_kwh (Patio Energy consumed)

## Change full name

You can also change the base sensor name with the `name` option

```yaml
powercalc:
  sensors:
    - entity_id: light.patio
      name: Patio Light
```

will create:

- sensor.patio_light_power (Patio light power)
- sensor.patio_light_energy (Patio light energy)
