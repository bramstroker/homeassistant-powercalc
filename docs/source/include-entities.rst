==============================
Dynamically including entities
==============================

Powercalc provides several methods to automatically include a bunch of entities in a group with the ``include`` option.
In addition to that you can use filters to exclude certain entities.

.. note::
    only entities will be included which are in the `supported models`_ list (these can be auto configured). You can combine ``include`` and ``entities`` to extend the group with custom configured entities.

Include
=======

Area
----

.. code-block:: yaml

  - platform: powercalc
    create_group: Outdoor
    include:
      area: outdoor

This can also be mixed with the ``entities`` option, to add or override entities to the group. i.e.

.. code-block:: yaml

  - platform: powercalc
    create_group: Outdoor
    include:
        area: outdoor
    entities:
      - entity_id: light.frontdoor
        fixed:

Group
-----

Includes entities from an existing Home Assistant `group <https://www.home-assistant.io/integrations/group/>`_ or `light group <https://www.home-assistant.io/integrations/light.group/>`_)

.. code-block:: yaml

  - platform: powercalc
    create_group: Livingroom lights
    include:
      group: group.livingroom_lights

Domain
------

.. code-block:: yaml

  - platform: powercalc
    create_group: All lights
    include:
      domain: light

Template
--------

.. code-block:: yaml

  - platform: powercalc
    create_group: All indoor lights
    include:
      template: {{expand('group.all_indoor_lights')|map(attribute='entity_id')|list}}

.. warning::
    The template option sometimes does not work correctly because of loading order of components in HA which powercalc cannot influence.
    So it's actually discouraged to use this and should only be used when you have no other options.

Filters
=======

Domain
------

.. code-block:: yaml

  - platform: powercalc
    create_group: Outdoor lights
    include:
      area: outdoor
      filter:
        domain: light

This will include only light entities from area outdoor.

You can also filter by multiple domains:

.. code-block:: yaml

  filter:
    domain:
      - light
      - switch
