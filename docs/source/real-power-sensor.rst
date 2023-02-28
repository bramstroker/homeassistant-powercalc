=================
Real power sensor
=================

In the yaml configuration (functionality not available through the webUI) you can add the following configuration
to use an existing power sensor and let powercalc create the energy sensors and utility meters for it:

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.toilet
        power_sensor_id: sensor.toilet_light_power

This also enables you to combine virtual power sensors (created with powercalc) and existing power sensors in your HA installation into
a group. Without this configuration option power_sensor_id that would not be possible.