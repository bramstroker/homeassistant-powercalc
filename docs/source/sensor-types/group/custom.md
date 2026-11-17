# Custom group

Create a group with a custom name and add individual power and energy sensors to it.

## Create group with GUI

You can create a new group with the GUI using this button.

[![config_flow_start](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

When this is not working.

- Go to `Settings` -> `Devices & Services`
- Click `Add integration`
- Search and click `Powercalc`

Select `Group` -> `Custom` and follow the instructions.

!!! tip

    After you have created a group you can directly assign a virtual power sensor to it when creating the power sensor by selecting the group in the `Group` field.
    You can also create group directly from the power sensor creation page, by filling in a custom group name in the `Group` field.

!!! warning

    Currently sensors registering negative energy values are not supported in groups.

### Recreate energy statistics when creating a group

Enable **Recreate statistics** under **Options** to give a new group the energy
history of its members. Disable **Start at zero** first: the form rejects using
both options together. **Create energy sensor** must be enabled and **Force
calculate energy** must be disabled. Recorder must be enabled and must record
the group's energy sensor.

Powercalc copies the hourly long-term statistics and the five-minute statistics
that Recorder still retains. For each interval, it converts the members' recorded
energy `sum` values to the group's unit and adds them:

| Interval | Sensor A's sum | Sensor B's sum | Group's sum |
| --- | ---: | ---: | ---: |
| 10:00–11:00 | 10 kWh | 5 kWh | 15 kWh |
| 11:00–12:00 | 12 kWh | 6 kWh | 18 kWh |

The group consumed **18 − 15 = 3 kWh** between these readings. Powercalc uses the
recorded `sum`, which includes consumption across meter resets, rather than
adding the raw meter readings or adding successive cumulative readings together.

- Each resolved member energy sensor is included once, including members of subgroups.
- If a member has a gap, its last known sum is carried forward. Before its first
  recorded statistic it contributes zero; missing consumption is not estimated.
- Older hourly values provide the baseline for retained five-minute statistics.
  An hourly value is only used after that hour has ended.
- If five-minute history is missing at the latest historical reading, Powercalc
  adds a single continuation checkpoint so Recorder retains the imported total.
- A member with no usable statistics starts contributing from its first available
  current reading. Its earlier consumption cannot be reconstructed.

The group energy sensor starts with the imported total plus changes since the
last recorded member readings, then continues counting normally. Its total may
therefore differ from the sum of the members' current meter readings, especially
when meters have reset. The members' own statistics remain unchanged.

This runs **once when the group is created**. Restarting Home Assistant, reloading
the group, or changing members does not repeat the import. The option is absent
from the settings of an existing group. Existing statistics under the new group's
entity ID are protected from being overwritten.

To inspect the calculation, run [**Powercalc: debug group**](../../actions/debug-group.md)
for the group's energy sensor. Its `statistics` section contains the import time,
unit, number of imported records, each member's last imported `sum` and meter
`state`, and members without usable history. The `end` timestamps identify the
end of each member's last imported interval in Unix seconds. This overview is a
snapshot of the import, not the group's current membership or live consumption.

## Create group with YAML

You can combine the `entities` option and `create_group` to group individual power sensors into a group.

```yaml
powercalc:
  sensors:
    - create_group: All hallway lights
      entities:
        - entity_id: light.hallway
        - entity_id: light.living_room
          linear:
            min_power: 0.5
            max_power: 8
```

This will create the following entities:

- sensor.hallway_power
- sensor.hallway_energy
- sensor.living_room_power
- sensor.living_room_energy
- sensor.all_hallway_lights_power (group sensor)
- sensor.all_hallway_lights_energy (group sensor)

### Nesting groups

You can also nest groups, this makes it possible to add an entity to multiple groups.

```yaml
powercalc:
  sensors:
    - create_group: All lights
      entities:
        - entity_id: light.a
        - entity_id: light.b
        - create_group: Upstairs lights
          entities:
            - entity_id: light.c
            - create_group: Bedroom Bob lights
              entities:
                - entity_id: light.d
```

Each group will have power sensors created for the following lights:

- All lights: `light.a`, `light.b`, `light.c`, `light.d`
- Upstairs lights: `light.c`, `light.d`
- Bedroom Bob lights: `light.d`

!!! warning

    a maximum nesting level of 5 groups is allowed!

## Hide individual sensors

To hide individual power sensors, and only have the group sensor available in HA GUI you can use the `hide_members` option.
When you used the GUI to create the group sensor you can use the `Hide members` toggle.

## Adding non powercalc sensors

Sometimes you want to add some power and energy sensors to your group which already exist in your HA installation.
For example some Zwave/Zigbee plug with built-in power monitoring.

In YAML you can use the `power_sensor_id` and `energy_sensor_id` options for that.
Let's assume your smart plug provides `sensor.heater_power` and `sensor.heater_kwh`. We want to add these to the group `Living Room`.

You can use the following configuration:

```yaml
powercalc:
  sensors:
    - create_group: Living Room
      entities:
        - power_sensor_id: sensor.heater_power
          energy_sensor_id: sensor.heater_kwh
        - entity_id: light.hallway #Powercalc sensor
```

!!! note

    When you don't supply `energy_sensor_id`, but only `power_sensor_id` powercalc tries to find a related energy sensor on the same device.
    When it cannot find one Powercalc will create an energy sensor.

If you use the GUI to create the groups you can use `Additional power entities` and `Additional energy entities` options.

![group_additional_entities](../../img/group_additional_entities.png)

Also see [Real power sensor](../real-power-sensor.md)

## Automatically include entities

Powercalc has some options to automatically include entities in your group matching certain criteria.
This can be useful to you don't have to manually specify each and every sensor.

See [include entities](include-entities.md) for more information.

## Force creating Riemann sum sensor

By default the group energy sensor created by Powercalc is a simple sum of the energy sensors of the individual entities.
When you have `create_energy_sensor: false` for the individual entities, the group energy sensor will not be created.
`force_calculate_group_energy` can be used to force the creation of a Riemann sum sensor for the group. This will take the group power sensor as the source and integrate it over time.

For example:

```yaml
powercalc:
  sensors:
    - create_group: all lights
      create_energy_sensor: true
      force_calculate_group_energy: true
      entities:
        - create_group: living lights
          create_energy_sensor: false
          entities:
            - entity_id: light.tv_lamp
            - entity_id: light.reading_light
            - ...
```

This way you can still create an energy sensor even when the individual entities don't have one.
When you are not interested in the individual energy sensors of each light this could be a good solution.

!!! important

    Beware that if your group also consists of [daily energy](../daily-energy.md) sensors the Riemann sum sensor will not be accurate, as it's could be missing the data of this sensor, because it does not always have a power sensor.
    So you only must use this option when the group power sensor contains all the power data from individual entities.

## Action get_group_entities

Powercalc provides an action [`Powercalc: get group entities`](../../actions/get-group-entities.md) to get all entity_id's of group members.

## Action debug_group

Powercalc also provides an action [`Powercalc: debug group`](../../actions/debug-group.md) to inspect the current group total and the current value of each member in the group unit.
