========
Playbook
========

The playbook strategy makes it possible to record power consumption over time and replay that in Home Assistant.
This is useful to implement power sensors for program based devices. For example Washing machines, dishwashers.
You can generate a playbook with the powercalc measure tool (todo link).

Currently only YAML is supported.

Configuration options
---------------------

+---------------+-------+--------------+----------+-----------------------------------------+
| Name          | Type  | Requirement  | Default  | Description                             |
+===============+=======+==============+==========+=========================================+
| playbooks     | dict  | **Required** |          | Mapping of playbook id's and file paths |
+---------------+-------+--------------+----------+-----------------------------------------+

Setup a power sensor with playbook support

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: sensor.dummy
        name: Washing machine
        playbook:
          playbooks:
            program1: playbooks/program1.csv
            program2: playbooks/program2.csv

Or reference your washing machine entity, this will also add the powercalc sensor to your washing machine device.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: switch.washing_machine
        playbook:
          playbooks:
            program1: playbooks/program1.csv
            program2: playbooks/program2.csv

Executing the playbook
----------------------

Powercalc provides two services which let's you control the playbook execution. `activate_playbook` and `stop_playbook`.
You can use this service in an automation to start the playbook.
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

