==============
Energy sensors
==============

An energy sensor provides a measurement in kWh, which is a measurement of power usage over time.
For example when you have a device of 1000 Watt running for 1 hour you have used 1000 Wh which equals to 1 kWh.
Powercalc can automatically create energy sensors for your virtual power meters. It uses the Riemann Sum helper for that.

By default energy sensors are created for all your powercalc power meters, but if you don't like that you can disable that with the ``create_energy_sensors`` option.

.. code-block:: yaml

    powercalc:
      create_energy_sensors: false

You can also set this option per sensor in YAML or when you use the GUI you can toggle this in the options.

Resetting energy sensor
~~~~~~~~~~~~~~~~~~~~~~~

Powercalc provides a service ``powercalc.reset_energy`` which you can call to reset energy sensors to 0 kWh.
You can call this service from the GUI (:guilabel:`Developer tools` -> :guilabel:`Services`) or use this in automations.