Virtual power sensors
=====================

To manually add virtual power sensors for your devices you can use the GUI or add some configuration to `configuration.yaml`.

Powercalc offers various calculation methods that can be used to establish a new virtual power sensor. Each method is suitable for specific use cases. To learn about all the configuration options, refer to the dedicated section.

- :doc:`strategies/fixed`
- :doc:`strategies/linear`
- :doc:`strategies/lut`
- :doc:`strategies/wled`

GUI
---

You can create new virtual power sensors with the GUI.

Just click the button to directly add a powercalc sensor:

.. image:: https://my.home-assistant.io/badges/config_flow_start.svg
   :target: https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc

When this is not working.

- Go to :guilabel:`Settings` -> :guilabel:`Devices & Services`
- Click :guilabel:`Add integration`
- Search and click :guilabel:`Powercalc`

Select :guilabel:`Virtual power (manual)` and follow the instructions

YAML
----

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

