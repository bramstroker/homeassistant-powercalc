# WLED

Supported domains: `light`

You can use the manual WLED strategy for light strips which are controlled by [WLED](https://github.com/Aircoookie/WLED).
WLED calculates estimated current based on brightness levels and the microcontroller (ESP) used.
Powercalc asks to input the voltage on which the lightstrip is running and optionally a power factor. Based on these factors, the wattage is calculated.

!!! important

    The brightness limiter must be turned on in WLED for this to work! Otherwise WLED will not provide an estimated current.

You can setup sensors both with YAML or GUI.
When you use the GUI, select the `Virtual power (manual)` sensor type, and `wled` in the "Calculation strategy" dropdown.
If you have multiple segments, select any of them as the source entity; selecting a helper group with all segments will cause a failure to find the current sensor, even if entity IDs match perfectly.

## Configuration options

| Name           | Type   | Requirement  | Default | Description                                     |
| -------------- | ------ | ------------ | ------- | ----------------------------------------------- |
| voltage        | float  | **Required** |         | Voltage for the lightstrip                      |
| power_factor   | float  | **Optional** | 0.9     | Power factor, between 0.1 and 1.0               |
| current_entity | string | **Optional** |         | Entity providing the estimated current, in mA   |

**Example**

```yaml
powercalc:
  sensors:
    - entity_id: light.wled_lightstrip
      wled:
        voltage: 5
```

## Providing your own current entity

By default Powercalc looks for the `Estimated current` sensor which the WLED integration creates for your device.
When that sensor does not exist you'll get the following error:

```
Skipping sensor setup: No estimated current entity found.
```

With `current_entity` you can point Powercalc to any sensor providing the estimated current in milliampere (mA) yourself.

```yaml
powercalc:
  sensors:
    - entity_id: light.wled_lightstrip
      wled:
        voltage: 5
        current_entity: sensor.wled_lightstrip_estimated_current
```

### Brightness limiter per output

When you configure the brightness limiter per output instead of globally, WLED reports the global maximum power as `0`.
The Home Assistant WLED integration uses that value to decide whether to create the `Estimated current` sensor, so no sensor is created,
even though WLED still calculates and reports the estimated current.

Until this is solved in the WLED integration, you can create a REST sensor which reads the value directly from your WLED device
and pass it to Powercalc using `current_entity`:

```yaml
sensor:
  - platform: rest
    name: WLED lightstrip estimated current
    resource: http://<your-wled-ip>/json/info
    value_template: "{{ value_json.leds.pwr }}"
    unit_of_measurement: mA
    device_class: current
    state_class: measurement
    scan_interval: 10

powercalc:
  sensors:
    - entity_id: light.wled_lightstrip
      wled:
        voltage: 5
        current_entity: sensor.wled_lightstrip_estimated_current
```
