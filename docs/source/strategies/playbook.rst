========
Playbook
========

The playbook strategy makes it possible to record power consumption over time and replay that in Home Assistant.
This is useful to implement power sensors for program based devices. For example Washing machines, dishwashers.
You can generate a playbook with the powercalc :doc:`measure tool </contributing/measure>`.

Currently only YAML is supported.

You must put your playbook in HA config directory and create a subdirectory ``powercalc/playbooks`` there.
So it could look like this:

::

    config
    ├── powercalc
    │   └── playbooks
    │       ├── playbook1.csv
    │       └── playbook2.csv

Configuration options
---------------------

+---------------+-------+--------------+----------+-----------------------------------------+
| Name          | Type  | Requirement  | Default  | Description                             |
+===============+=======+==============+==========+=========================================+
| playbooks     | dict  | **Required** |          | Mapping of playbook id's and file paths |
+---------------+-------+--------------+----------+-----------------------------------------+

Setup a power sensor with playbook support.
The examples below will both create a ``sensor.washing_machine_power``

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: switch.washing_machine
        playbook:
          playbooks:
            program1: program1.csv
            program2: program2.csv

this will also add the powercalc sensor to your washing machine device.

or when you don't have an entity to bind to, just use dummy and define a name.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: sensor.dummy
        name: Washing machine
        playbook:
          playbooks:
            ...


Executing the playbook
----------------------

To start executing a playbook you'll have to utilize HA automations.
Powercalc provides two services which let's you control the playbook execution. `activate_playbook` and `stop_playbook`.
For example to start the playbook when your washing machine enters a specific program use an automation similar as below.

.. code-block:: yaml

    description: "Activate powercalc playbook when Washing machine starts program"
    mode: single
    trigger:
      - platform: state
        entity_id:
          - sensor.washing_machine_job_state
        to: program1
    condition: []
    action:
      - service: powercalc.calibrate_energy
        data:
          value: program1
        target:
          entity_id: sensor.waching_machine_power

Playbook structure
------------------

A playbook file must be a CSV file with 2 columns.
- elapsed time in seconds
- power value in W

::

    0.5,70
    2,90
    4,25.5

When running this playbook the power sensor state will go to 70W after 0.5 seconds, 90W after 2 seconds and 25.5W after 4 seconds.
All these timing are relative to the start of the playbook. So when the playbook starts at 18:00:00 the final step will be executed at 18:00:04


