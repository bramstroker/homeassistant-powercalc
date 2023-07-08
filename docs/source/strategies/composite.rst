=========
Composite
=========

The composite strategy allows you to create power sensor which contains of multiple strategies.
For each strategy you can setup conditions which indicate when the strategy should be applied.
So for example you could use the ``fixed`` strategy when a certain condition applies, and the ``linear`` when another condition applies.
For the conditions the same engine is used as in HA automations and scripts. See https://www.home-assistant.io/docs/scripts/conditions/

Currently this is a YAML only feature

Configuration options
---------------------

+---------------+-------+--------------+----------+------------------------------------+
| Name          | Type  | Requirement  | Default  | Description                        |
+===============+=======+==============+==========+====================================+
| strategies    | list  | **Required** |          | List of objects with strategy configuration and condition |         |
+---------------+-------+--------------+----------+------------------------------------+

Usage
-----

Let's start with a simple example:

.. code-block:: yaml

    powercalc:
      sensors:
        - entity_id: switch.heater
          composite:  # This indicates the composite strategy is used
            - condition:
                condition: state
                entity_id: select.heater_mode
                state: high
              fixed:
                power: 1000
            - fixed:
                power: 500

This will create a power sensor `sensor.heater_power`. Whenever the `select.heater_mode` is high the power sensor will be 1000 and in all other cases 500.

.. note::
    Strategies will be checked in the order in which they were registered. Until the condition matches.

You can mix/match strategies and also use composed conditions using `OR` and `AND`.
For example:


.. code-block:: yaml

    powercalc:
      sensors:
        - entity_id: light.test
          composite:
            # First strategy (fixed) using nested AND and OR conditions
            - condition:
                condition: and
                conditions:
                  - condition: state
                    entity_id: binary_sensor.test
                    state: on
                  - condition: or
                    conditions:
                      - condition: numeric_state
                        entity_id: sensor.test
                        above: 20
                        below: 40
                      - condition: template
                        value_template: "{{ is_state('sensor.test2', 'test') }}"
              fixed:
                power: 10
            # Second strategy (linear)
            - condition:
                condition: state
                entity_id: binary_sensor.test
                state: off
              linear:
                min_power: 20
                max_power: 40


When no condition matches for any strategy the power sensor will become ``unavailable`` or when the ``light.test`` is OFF powercalc will look at the ``standby_power``
You can omit ``condition`` on the last register strategy so that will always be used as a fallback.

.. warning::
    Don't omit ``condition`` field on any strategy other than the last as that will cause the strategy chain to stop at that one.

