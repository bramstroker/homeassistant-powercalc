==============================
Dynamically including entities
==============================

Powercalc provides several methods to automatically include a bunch of entities in a group with the ``include`` option.

.. note::
    only entities will be included which are in the `supported models`_ list (these can be auto configured). You can combine ``include`` and ``entities`` to extend the group with custom configured entities.

Area
----

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: Outdoor
        include:
          area: outdoor

This can also be mixed with the ``entities`` option, to add or override entities to the group. i.e.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: Outdoor
        include:
          area: outdoor
        entities:
          - entity_id: light.frontdoor
            fixed:
              power: 100

Group
-----

Includes entities from a Home Assistant `group <https://www.home-assistant.io/integrations/group/>`_ or `light group <https://www.home-assistant.io/integrations/light.group/>`_)

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: Livingroom lights
        include:
          group: group.livingroom_lights

Template
--------

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: All indoor lights
        include:
          template: {{expand('group.all_indoor_lights')|map(attribute='entity_id')|list}}

Domain
------

.. code-block:: yaml

    sensor:
      - platform: powercalc
        create_group: All lights
        include:
          domain: light