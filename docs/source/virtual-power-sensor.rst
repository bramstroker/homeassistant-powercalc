Virtual power sensors
=====================

To manually add virtual power sensors for your devices you can use the GUI or add some configuration to `configuration.yaml`.

Powercalc offers various calculation methods that can be used to establish a new virtual power sensor. Each method is suitable for specific use cases. To learn about all the configuration options, refer to the dedicated section.

.. toctree::
   :maxdepth: 1

   strategies/fixed
   strategies/linear
   strategies/lut
   strategies/playbook
   strategies/wled
   strategies/composite

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

Select :guilabel:`Virtual power (manual)` and follow the instructions.

After you have walked through the wizard the new powercalc sensor must be created and appear in the list.
When you click on it you can see the entities which are created.
Some options can be changed afterwards, just click :guilabel:`Configure`

YAML
----

To create a power sensor with YAML you'll have to add a new entry under the ``sensor:`` line in `configuration.yaml`.

Most basic example:

.. code-block:: yaml

    powercalc:
      sensors:
        - entity_id: light.my_light
          fixed:
            power: 20

Tip: You can also setup multiple sensors in one go using the ``entities`` option.

.. code-block:: yaml

    powercalc:
      sensors:
        - entities:
            - entity_id: light.my_light
              fixed:
                power: 20
            - entity_id: light.my_light2
              linear:
                min_power: 2
                max_power: 9

For all the possible options see the strategy sections as linked above, :doc:`configuration/sensor-configuration` and the rest of the Powercalc documentation.

.. important::

    After changing the configuration you'll need to restart HA to get your power sensors to appear.

