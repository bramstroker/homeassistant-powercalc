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

| Name         | Type  | Requirement  | Default | Description                       |
| ------------ | ----- | ------------ | ------- | --------------------------------- |
| voltage      | float | **Required** |         | Voltage for the lightstrip        |
| power_factor | float | **Optional** | 0.9     | Power factor, between 0.1 and 1.0 |

**Example**

```yaml
powercalc:
  sensors:
    - entity_id: light.wled_lightstrip
      wled:
        voltage: 5
```
