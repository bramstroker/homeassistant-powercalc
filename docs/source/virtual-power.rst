Virtual power sensors
=====================

To manually add virtual power sensors for your devices you can use the GUI or add some configuration to `configuration.yaml`.

Powercalc provides different calculation strategies which you can utilize to set up a new virtual power sensor.
Each strategy has it's own use case. If you want to know all about the configuration options check the dedicated section.

- Fixed
- Linear
- LUT
- WLED

GUI
===

You can create new virtual power sensors with the GUI.
TODO, images / video / text

YAML
======

To create a power sensor with YAML you'll have to add a new entry under the ``sensor:`` line in `configuration.yaml`.

Most basic example:

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.my_light
        fixed:
          power: 20

Tip: You can also setup multiple sensors in one go using the ``entities`` option.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entities:
          - entity_id: light.my_light
            fixed:
              power: 20
          - entity_id: light.my_light2
            linear:
              min_power: 2
              max_power: 9

For all the possible options see the strategy sections as linked above and the rest of the Powercalc documentation.

.. important::

    After changing the configuration you'll need to restart HA to get your power sensors to appear.

