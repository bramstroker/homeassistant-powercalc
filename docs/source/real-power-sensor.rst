=================
Real power sensor
=================

To use an existing power sensor and let powercalc create the energy sensors and utility meters for it, 
you'll have to add a new entry under ``sensor:`` in `configuration.yaml` (functionality not available through the webUI).

.. code-block:: yaml

  - platform: powercalc
    entity_id: light.toilet
    power_sensor_id: sensor.toilet_light_power
    force_energy_sensor_creation: true # optional

This also enables you to combine virtual power sensors (created with powercalc) and existing power sensors in your HA installation into
a group. Without this configuration option power_sensor_id that would not be possible.

If you don't define `force_energy_sensor_creation` or you set it to `false` an energy sensor will not be created if the device already
has an energy sensor. This can be a problem if you want to create an energy sensor for an MQTT device with multiple energy and power
sensors already in it.
