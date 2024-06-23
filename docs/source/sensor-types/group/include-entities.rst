==============================
Dynamically including entities
==============================

Powercalc provides several methods to automatically include a bunch of entities in a group with the ``include`` option.
In addition to that you can use filters to exclude certain entities.

.. note::
    only entities will be included which are in the `supported models`_ list (these can be auto configured). You can combine ``include`` and ``entities`` to extend the group with custom configured entities.

.. important::
    Powercalc will include any power sensors found in your HA installation matching the include rules. When you don't want that see `Exclude non powercalc sensors`_

Include
=======

Area
----

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Outdoor
          include:
            area: outdoor

This can also be mixed with the ``entities`` option, to add or override entities to the group. i.e.

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Outdoor
          include:
            area: outdoor
          entities:
            - entity_id: light.frontdoor
              fixed:
                power: 100

Group
-----

Includes entities from an existing Home Assistant `group <https://www.home-assistant.io/integrations/group/>`_ or `light group <https://www.home-assistant.io/integrations/light.group/>`_)

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Livingroom lights
          include:
            group: group.livingroom_lights

Domain
------

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: All lights
          include:
            domain: light

You might also filter by multiple domains:

.. code-block:: yaml

  powercalc:
      sensors:
        - create_group: All lights
          include:
            domain:
              - light
              - switch

Wildcard
--------

Match certain entity id's by a wildcard pattern

``*`` matches any character
``?`` matches a single character

When you don't supply any of the above wildcard the filter checks for an exact match of the entity_id

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Office spots
          include:
            wildcard: light.office_spot_*

Template
--------

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: All indoor lights
          include:
            template: {{expand('group.all_indoor_lights')|map(attribute='entity_id')|list}}

.. warning::
    The template option sometimes does not work correctly because of loading order of components in HA which powercalc cannot influence.
    So it's actually discouraged to use this and should only be used when you have no other options.

All
---

Include all powercalc sensors and other power sensors of the HA installation in the group.
You can combine that with the filters mentioned below.

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: General
          include:
            all:

Filters
=======

Besides the base filters described above which build the base include you can also apply additional filters to further narrow down the list of items.
These filters accept the same configuration as described above.

For example to include all light entities from area outdoor.

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Outdoor lights
          include:
            area: outdoor
            filter:
              domain: light

AND/OR
------

You can also chain nested filter using and / or construction:

.. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Outdoor lights
          include:
            area: outdoor
            filter:
              or:
                - domain: light
                - wildcard: switch.pond
                - and:
                  - domain: binary_sensor
                  - wildcard: "*swimming_pool*"

Exclude non powercalc sensors
=============================

By default all the include options will include any power and/or energy sensor from your system, also power sensors provided by other integrations.
When you don't want that behaviour you can set ``include_non_powercalc_sensors`` to ``false``.

.. code-block:: yaml

    .. code-block:: yaml

    powercalc:
      sensors:
        - create_group: Outdoor lights
          include:
            area: outdoor
            include_non_powercalc_sensors: false

You can also set this option globally:

.. code-block:: yaml

    .. code-block:: yaml

    powercalc:
      include_non_powercalc_sensors: false
