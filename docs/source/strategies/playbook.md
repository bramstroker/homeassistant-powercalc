# Playbook

## Overview

The playbook strategy allows you to record power consumption patterns over time and replay them in Home Assistant. This powerful feature is particularly useful for implementing power sensors for program-based devices such as washing machines, dishwashers, and other appliances with predictable power consumption cycles.

With playbooks, you can:
- Simulate power consumption patterns for various device programs
- Automatically trigger different power profiles based on device states
- Create realistic power consumption models for devices without built-in power monitoring

You can generate a playbook using the powercalc [measure tool](../contributing/measure.md) or create one manually based on known power consumption patterns.

## Setup

You can configure playbook sensors either through YAML configuration or the Home Assistant GUI:
- **GUI method**: Select `playbook` in the calculation_strategy dropdown during sensor setup
- **YAML method**: Follow the configuration examples below

### File Structure

Playbook files must be stored in the Home Assistant config directory under a specific subdirectory: `powercalc/playbooks/`.

Your directory structure should look like this:

```
config/
├── powercalc/
│   └── playbooks/
│       ├── program1.csv
│       ├── program2.csv
│       └── other_playbooks.csv
```

## Configuration Options

| Name          | Type   | Requirement  | Default | Description                                                                              |
| ------------- | ------ | ------------ | ------- | ---------------------------------------------------------------------------------------- |
| playbooks     | dict   | **Required** |         | Mapping of playbook IDs to file paths                                                    |
| autostart     | string | **Optional** |         | Key of the playbook to start automatically when Home Assistant starts                    |
| repeat        | bool   | **Optional** | false   | When set to `true`, the playbook will restart after completion                           |
| state_trigger | dict   | **Optional** |         | Activates a playbook when the entity reaches a specific state (state → playbook_id map)  |

## Configuration Examples

### Basic Setup with Existing Entity

This example creates a power sensor (`sensor.washing_machine_power`) linked to an existing entity:

```yaml
powercalc:
  sensors:
    - entity_id: switch.washing_machine
      playbook:
        playbooks:
          program1: program1.csv
          program2: program2.csv
```

This configuration will automatically add the powercalc sensor to your washing machine device in the Home Assistant UI.

### Standalone Sensor (No Existing Entity)

If you don't have an entity to bind to, you can create a standalone sensor:

```yaml
powercalc:
  sensors:
    - entity_id: sensor.dummy
      name: Washing Machine
      playbook:
        playbooks:
          program1: washing_machine_normal.csv
          program2: washing_machine_eco.csv
          quick_wash: washing_machine_quick.csv
```

### Auto-Starting Playbook with Repeat

For devices with cyclical power patterns (like refrigerators), you can use the `autostart` and `repeat` options:

```yaml
powercalc:
  sensors:
    - entity_id: sensor.dummy
      name: Refrigerator
      playbook:
        playbooks:
          cycle: refrigerator_cycle.csv
        autostart: cycle
        repeat: true
```

## State-Based Playbook Activation

You can automatically activate different playbooks based on the state of the entity using the `state_trigger` option:

```yaml
powercalc:
  sensors:
    - entity_id: media_player.sonos
      name: Sonos Speaker
      playbook:
        playbooks:
          idle: sonos_idle.csv
          playing: sonos_playing.csv
          paused: sonos_paused.csv
        state_trigger:
          idle: idle
          playing: playing
          paused: paused
```

In this example, different power consumption profiles will be activated automatically when the Sonos speaker changes state.

## Manual Playbook Control

To manually control playbook execution, you can use Home Assistant automations with the [`activate_playbook`](../actions/activate-playbook.md) and [`stop_playbook`](../actions/stop-playbook.md) actions.

Example automation to start a specific washing machine program:

```yaml
description: "Activate washing machine power playbook when program starts"
mode: single
trigger:
  - platform: state
    entity_id:
      - sensor.washing_machine_job_state
    to: program1
action:
  - action: powercalc.activate_playbook
    data:
      playbook_id: program1
    target:
      entity_id: sensor.washing_machine_power
```

## Playbook File Format

A playbook file must be a CSV file with 2 columns:
1. Elapsed time in seconds
2. Power value in watts (W)

Example playbook content:
```
0.5,70
2,90
4,25.5
10,120
15,80
20,0
```

When this playbook runs:
- At 0.5 seconds: Power will be 70W
- At 2 seconds: Power will increase to 90W
- At 4 seconds: Power will decrease to 25.5W
- And so on...

All timings are relative to when the playbook starts. For example, if the playbook starts at 18:00:00, the final step (20 seconds) will be executed at 18:00:20.
