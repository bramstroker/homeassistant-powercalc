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

## Follow device name

Open the **Global configuration → Power sensor** section and enable **Follow device name**
to use device naming for supported virtual power sensors configured through the UI.
This option is off by default, including for existing entries. Changing the global setting
reloads existing entries to apply it.

This setting applies globally; there is no per-entry toggle. Unsupported configurations
keep their configured names.

Powercalc uses Home Assistant's device naming for the generated power, energy, standby energy,
utility meter, cost, and tariff selection entities. For example, an entity named **Patio Power**
will become **Terrace Power** when you rename its assigned device from **Patio** to **Terrace**.
Renaming the source entity alone does not rename these entities.

Entity IDs, unique IDs, energy totals, and statistics remain unchanged. Custom names set in the
entity settings are preserved and follow Home Assistant's normal naming rules.
The Powercalc configuration title and stored name remain unchanged; turning the option off
returns to the configured naming behavior. Home Assistant may still format names using its own
device naming settings.

The first version supports virtual power entries associated with a named device and using the
standard display-name patterns. It does not support YAML entries, groups, standalone cost entries,
named source channels, multi-switch configurations, or multiple virtual power entries assigned to
the same device. These configurations retain their existing naming behavior.

Custom entity-ID patterns can be used if their corresponding friendly-name patterns explicitly
retain the standard display names, such as `power_sensor_friendly_naming: "{} power"`.

If the device is missing at startup, or the configuration no longer supports this option,
Powercalc logs a warning and uses the configured names for that load. The option remains enabled
and is tried again on the next reload or restart.
