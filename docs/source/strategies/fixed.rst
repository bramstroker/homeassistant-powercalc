Fixed
=====

When you have an appliance which only can be set on and off you can use this mode.
You need to supply a single watt value in the configuration which will be used when the device is ON
Also we provide an option to define power values for certain entity states.

You can setup sensors both with YAML or GUI.
When you use the GUI select `fixed` in the calculation_strategy dropdown.

Configuration options
---------------------

+--------------+--------+--------------+--------------------------------------------------------------------------------+
| Name         | Type   | Requirement  | Description                                                                    |
+==============+========+==============+================================================================================+
| power        | float  | **Optional** | Power usage when the appliance is turned on (in watt). Can also be a template_ |
+--------------+--------+--------------+--------------------------------------------------------------------------------+
| states_power | dict   | **Optional** | Power usage per entity state. Values can also be a template_                   |
+--------------+--------+--------------+--------------------------------------------------------------------------------+

**Simplest example**

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.nondimmabled_bulb
        fixed:
          power: 20

**Using a template for the power value**

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.bathroom
        fixed:
          power: "{{states('input_number.bathroom_watts')}}"

When you don't have a source entity or helper (ex. `input_boolean`) to bind on and you just want the power sensor to reflect the template value you can use `sensor.dummy` as the entity_id

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: sensor.dummy
        fixed:
          power: "{{states('input_number.bathroom_watts')}}"

Power per state
---------------
The `states_power` setting allows you to specify a power per entity state. This can be useful for example on Sonos devices which have a different power consumption in different states.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: media_player.sonos_living
        fixed:
          states_power:
            playing: 8.3
            paused: 2.25
            idle: 1.5

> Remark: You cannot use `off` in states_power as this is handled separately by powercalc. You'll need to use `standby_power` to indicate the power when the device is off.

You can also use state attributes. Use the `|` delimiter to seperate the attribute and value. Here is en example:

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: media_player.sonos_living
        fixed:
          power: 12
          states_power:
            media_content_id|Spotify: 5
            media_content_id|Youtube: 10

When no match is found in `states_power` lookup than the configured `power` will be considered.

.. _template: https://www.home-assistant.io/docs/configuration/templating/