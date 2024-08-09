# Real power sensor

Powercalc also provides possibilities to create energy sensors (and optionally utility meters) for existing power sensors in your installation.
You could also create them with the built-in helpers HA provides, but Powercalc makes it even more easy and you can also includes existing power sensors in Powercalc groups this way.
The energy sensors can be added to the energy dashboard.

You can create this either with the YAML or GUI.

## GUI

Just click this button to start the configuration flow:

[![config_flow_start](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

Select `Energy from real power sensor` and follow the instructions.

## YAML

In the yaml configuration you can add the following configuration
to use an existing power sensor and let powercalc create the energy sensors and utility meters for it:

```yaml
powercalc:
  sensors:
    - entity_id: light.toilet
      power_sensor_id: sensor.toilet_light_power
      force_energy_sensor_creation: true # optional
```

This also enables you to combine virtual power sensors (created with powercalc) and existing power sensors in your HA installation into
a YAML group. Without this configuration option power_sensor_id that would not be possible.

When using `force_energy_sensor_creation` you need to provide either a source entity (`entity_id`) or a `name` for the energy sensor.
If you don't provide this Powercalc has no way to determine how the energy sensor should be named.

!!! note

    If you don't define `force_energy_sensor_creation` or you set it to `false` an energy sensor will not be created if the device already has an energy sensor. This can be a problem if you want to create an energy sensor for an MQTT device with multiple energy and power sensors already in it.
