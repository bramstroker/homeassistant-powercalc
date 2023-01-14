======
Groups
======

Powercalc provides several options to group individual power sensors into a single one which sums the total. This can be very useful to get a glance about the consumption of all your lights together for example.

Create group with GUI
---------------------

Todo: write

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