=========
Composite
=========

The composite strategy allows you to compose the power calculation of multiple strategies.
So you could use the ``fixed`` strategy when a certain condition applies, and the ``linear`` when another condition applies.

Currently this is a YAML only feature

Configuration options
---------------------

+---------------+-------+--------------+----------+------------------------------------+
| Name          | Type  | Requirement  | Default  | Description                        |
+===============+=======+==============+==========+====================================+
| strategies    | list  | **Required** |          | List of objects with strategy configuration and condition |         |
+---------------+-------+--------------+----------+------------------------------------+

**Example**

.. code-block:: yaml

    powercalc:
      sensors:
        - entity_id: light.test
          composite:
            strategies:
              - condition:

