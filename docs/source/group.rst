======
Groups
======

Powercalc provides several options to group individual power sensors into a single one which sums the total.
This can be very useful to get a glance about the consumption of all your lights together for example.

Create group with GUI
---------------------

You can create a new group with the GUI using this button.

.. image:: https://my.home-assistant.io/badges/config_flow_start.svg
   :target: https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc

When this is not working.

- Go to :guilabel:`Settings` -> :guilabel:`Devices & Services`
- Click :guilabel:`Add integration`
- Search and click :guilabel:`Powercalc`

Select :guilabel:`Group` and follow the instructions.

.. tip::
    After you have created a group you can directly assign a virtual power sensor to it when creating the power sensor by selecting the group in the :guilabel:`Group` field

Create group with YAML
----------------------

You can combine the ``entities`` option and ``create_group`` to group individual power sensors into a group.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: All hallway lights
        entities:
          -  entity_id: light.hallway
          -  entity_id: light.living_room
             linear:
               min_power: 0.5
               max_power: 8

This will create the following entities:

- sensor.hallway_power
- sensor.hallway_energy
- sensor.living_room_power
- sensor.living_room_energy
- sensor.all_hallway_lights_power (group sensor)
- sensor.all_hallway_lights_energy (group sensor)

Nesting groups
^^^^^^^^^^^^^^

You can also nest groups, this makes it possible to add an entity to multiple groups.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: All lights
        entities:
          - entity_id: light.a
          - entity_id: light.b
          - create_group: Upstairs lights
            entities:
              - entity_id: light.c
              - create_group: Bedroom Bob lights
                entities:
                  - entity_id: light.d

Each group will have power sensors created for the following lights:

- All lights: `light.a`, `light.b`, `light.c`, `light.d`
- Upstairs lights: `light.c`, `light.d`
- Bedroom Bob lights: `light.d`

.. warning::
    a maximum nesting level of 5 groups is allowed!

Hide individual sensors
-----------------------

To hide individual power sensors, and only have the group sensor available in HA GUI you can use the ``hide_members`` option.
When you used the GUI to create the group sensor you can use the :guilabel:`Hide members` toggle.

Adding non powercalc sensors
----------------------------

Sometimes you want to add some power and energy sensors to your group which already exist in your HA installation.
For example some Zwave/Zigbee plug with built-in power monitoring.

In YAML you can use the ``power_sensor_id`` and ``energy_sensor_id`` options for that.
Let's assume your smart plug provides `sensor.heater_power` and `sensor.heater_kwh`. We want to add these to the group `Living Room`.

You can use the following configuration:

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: Living Room
        entities:
          - power_sensor_id: sensor.heater_power
            energy_sensor_id: sensor.heater_kwh
          - entity_id: light.hallway #Powercalc sensor

.. note::
    When you don't supply ``energy_sensor_id``, but only ``power_sensor_id`` powercalc tries to find a related energy sensor on the same device.
    When it cannot find one Powercalc will create an energy sensor.

If you use the GUI to create the groups you can use :guilabel:`Additional power entities` and :guilabel:`Additional energy entities` options.

.. image:: img/group_additional_entities.png

Also see :doc:`real-power-sensor`

Domain groups
-------------

Powercalc makes it easy to create a group sensors for all entities of a given domain with the ``create_domain_groups`` option.
For example let's assume you want group sensors for all your lights and media players you can use the following configuration.

.. code-block:: yaml

    powercalc:
      create_domain_groups:
        - light
        - media_player

.. note::
    This will only include all virtual power sensors created with powercalc, not any other power sensors already available in your HA installation.

Automatically include entities
------------------------------

Powercalc has some options to automatically include entities in your group matching certain criteria.
This can be useful to you don't have to manually specify each and every sensor.

See :doc:`include-entities` for more information.