============
Multi Switch
============

The multi switch strategy allows you to combine the self usage of multiple switches into a single entity.
This can be used for example to make a profile for Tp-Link HS300 power strip.

Configuration options
---------------------

+---------------+---------+--------------+----------+------------------------------------------------------------------------------------------+
| Name          | Type    | Requirement  | Default  | Description                                                                              |
+===============+=========+==============+==========+==========================================================================================+
| entities      | dict    | **Required** |          | Provide a list of the individual switch entities                                         |
+---------------+---------+--------------+----------+------------------------------------------------------------------------------------------+
| power         | decimal | **Optional** |          | Power for one outlet when it is switched on                                              |
+---------------+---------+--------------+----------+------------------------------------------------------------------------------------------+
| power_off     | decimal | **Optional** |          | Power for one outlet when it is switched off                                             |
+---------------+--------+---------------+----------+------------------------------------------------------------------------------------------+

.. code-block:: yaml

    powercalc:
      sensors:
        - name: "My outlet self usage"
          multi_switch:
            entities:
              - switch.outlet_1
              - switch.outlet_2
              - switch.outlet_3
            power_off: 0.25
            power: 0.5

In this example, when all the switches are turned on, the power usage will be 0.5W * 3 = 1.5W
When only `switch.outlet_1` is turned on, the power usage will be 0.5W + 0.25W + 0.25W = 1W
