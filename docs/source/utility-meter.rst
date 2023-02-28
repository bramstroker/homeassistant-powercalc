==============
Utility meters
==============

The energy sensors created by the component will keep increasing the total kWh, and never reset.
When you want to know the energy consumed the last 24 hours, or last month you can use the `utility_meter <https://www.home-assistant.io/integrations/utility_meter/>`_ component of Home Assistant. Powercalc allows you to automatically create utility meters for all your powercalc sensors with a single line of configuration.

Toggling utility meter creation on/off can also be done when creating power sensors with the GUI on a per sensor basis.

To create utility meters for all powercalc sensors globally add the following configuration to `configuration.yaml`.

.. code-block:: yaml

    powercalc:
      create_utility_meters: true

By default utility meters are created for ``daily``, ``weekly``, ``monthly`` cycles.
You can change this behaviour with the ``utility_meter_types`` configuration option.

.. code-block:: yaml

    powercalc:
      create_utility_meters: true
      utility_meter_types:
        - daily
        - yearly

.. note::
    A note on :doc:`naming`.
    The utility meters have the same name as your energy sensor, but are extended by the meter cycle.
    Assume you have a light `light.floorlamp_livingroom`, than you should have the following sensors created:

    - `sensor.floorlamp_livingroom_power`
    - `sensor.floorlamp_livingroom_energy`
    - `sensor.floorlamp_livingroom_energy_daily`
    - `sensor.floorlamp_livingroom_energy_weekly`
    - `sensor.floorlamp_livingroom_energy_monthly`