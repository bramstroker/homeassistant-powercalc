# Playbook

The playbook strategy makes it possible to record power consumption over time and replay that in Home Assistant.
This is useful to implement power sensors for program based devices. For example Washing machines, dishwashers.
You can generate a playbook with the powercalc [measure tool](../contributing/measure.md).

You can setup sensors both with YAML or GUI.
When you use the GUI select `playbook` in the calculation_strategy dropdown.

You must put your playbook in HA config directory and create a subdirectory `powercalc/playbooks` there.
So it could look like this:

```
config
├── powercalc
│   └── playbooks
│       ├── playbook1.csv
│       └── playbook2.csv
```

## Configuration options

| Name          | Type   | Requirement  | Default | Description                                                                              |
| ------------- | ------ | ------------ | ------- | ---------------------------------------------------------------------------------------- |
| playbooks     | dict   | **Required** |         | Mapping of playbook id's and file paths                                                  |
| autostart     | string | **Optional** |         | key of the playbook which you want to start when HA starts.                              |
| repeat        | bool   | **Optional** | false   | Set to `true` when you want to restart the playbook after it completes                   |
| state_trigger | dict   | **Optional** |         | Activate a playbook when the entity has a certain state. Mapping of state -> playbook_id |

Setup a power sensor with playbook support.
The example below will create entity `sensor.washing_machine_power`

```yaml
powercalc:
  sensors:
    - entity_id: switch.washing_machine
      playbook:
        playbooks:
          program1: program1.csv
          program2: program2.csv
```

this will also add the powercalc sensor to your washing machine device.

or when you don't have an entity to bind to, just use dummy and define a name.

```yaml
powercalc:
  sensors:
    - entity_id: sensor.dummy
      name: Washing machine
      playbook:
        playbooks:
          ...
```

Example using `autostart` and `repeat` options:

```yaml
powercalc:
  sensors:
    - entity_id: sensor.dummy
      name: Refrigerator
      playbook:
        playbooks:
          playbook: refrigerator.csv
      autostart: playbook
      repeat: true
```

## Active playbook based on state trigger

To activate a playbook based on a state trigger you can use the `state_trigger` option.
This option is a mapping of state -> playbook_id.
When the entity enters the state the playbook will be activated.

```yaml
powercalc:
  sensors:
    - entity_id: sensor.sonos
      name: Sonos
      playbook:
        playbooks:
          idle: sonos_play/idle.csv
          paused: sonos_play/paused.csv
        state_trigger:
          idle: idle
          paused: paused
```

## Manually executing the playbook

To start executing a playbook you'll have to utilize HA automations.
Powercalc provides two actions which let's you control the playbook execution. `activate_playbook` and `stop_playbook`.
For example to start the playbook when your washing machine enters a specific program use an automation similar as below.

```yaml
description: "Activate powercalc playbook when Washing machine starts program"
mode: single
trigger:
  - platform: state
    entity_id:
      - sensor.washing_machine_job_state
    to: program1
condition: []
action:
  - action: powercalc.activate_playbook
    data:
      playbook_id: program1
    target:
      entity_id: sensor.waching_machine_power
```

## Playbook structure

A playbook file must be a CSV file with 2 columns.
\- elapsed time in seconds
\- power value in W

```
0.5,70
2,90
4,25.5
```

When running this playbook the power sensor state will go to 70W after 0.5 seconds, 90W after 2 seconds and 25.5W after 4 seconds.
All these timing are relative to the start of the playbook. So when the playbook starts at 18:00:00 the final step will be executed at 18:00:04
