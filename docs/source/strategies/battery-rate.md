# Battery rate

The `battery_rate` strategy estimates charging power from changes in a battery percentage sensor.
It is useful when a charger changes speed but the device does not expose its charging mode.
This strategy is available in YAML and library profiles; there is no manual configuration form yet.

Power is calculated as:

```text
power [W] = base_power + max(0, battery_now - battery_window_start) * 3600/window * energy_per_percent
```

The battery percentage is held constant between readings. `window` is measured in seconds and
`energy_per_percent` in Wh per displayed percentage point. The coefficient must be measured for
the device; it is not the battery's nominal capacity divided by 100, because charging losses and
the device's displayed percentage also affect it. Battery ageing or replacement can change the coefficient.

## Configuration

| Option | Required | Default | Description |
|---|---|---|---|
| `entity_id` | Yes | | Battery percentage entity, reporting a number from 0 to 100. |
| `energy_per_percent` | Yes | | Positive charging energy per displayed percentage point, in Wh/%. |
| `base_power` | No | `0` | Non-negative baseline power in W, included in the result. |
| `window` | No | `600` | Positive smoothing window in seconds. |
| `max_power` | No | No limit | Maximum total power of this strategy, including `base_power`, in W. Must be at least `base_power`. |

For example, while the battery gains 5 percentage points over 10 minutes, a coefficient of
0.96 Wh/% and baseline of 3.5 W produce `3.5 + 5 * 6 * 0.96 = 32.3 W`.
The following values are illustrative and require calibration for your device.

```yaml
powercalc:
  sensors:
    - entity_id: vacuum.robot
      composite:
        - condition:
            condition: state
            state: docked
          battery_rate:
            entity_id: sensor.robot_battery
            energy_per_percent: 0.96
            base_power: 3.5
            window: 600
            max_power: 60
        - fixed:
            power: 0
```

Use the device's docked or charging status for the condition. Avoid a condition such as
`battery < 100`: the delayed contribution after the last percentage increment helps account for
the energy used earlier in the charge. Once the percentage stops changing, the contribution above
`base_power` reaches zero within one window, plus up to one periodic update interval.
Powercalc recalculates at least every 60 seconds, or every `window` seconds for shorter windows.
No derivative helper or separate `power_update_interval` setting is needed.

A `battery_rate` block can also be used directly on a sensor. It then applies whenever the parent
source is active; add a composite condition when charging needs to be distinguished from other states.

## Library profiles

The same configuration works in a composite profile, including related entity placeholders:

```json
{
  "calculation_strategy": "composite",
  "composite_config": [
    {
      "condition": {"condition": "state", "state": "docked"},
      "battery_rate": {
        "entity_id": "[[entity_by_device_class:battery]]",
        "energy_per_percent": 0.96,
        "base_power": 3.5,
        "window": 600,
        "max_power": 60
      }
    },
    {"fixed": {"power": 0}}
  ]
}
```

A standalone profile uses `calculation_strategy: battery_rate` with `battery_rate_config`.
Use composite `sum_all` to add independent contributions such as mop drying. Keep that contribution
out of `base_power` and the measured charging coefficient to avoid counting it twice. `max_power`
limits only its own strategy's contribution, not the composite total.

## Startup, interruptions and accuracy

After setup, reload or restart, the first valid reading supplies the starting percentage. There is
no Recorder history lookup or restored rate. The full window remains the denominator during startup,
so the estimate initially runs low rather than assuming the battery started at 0%.

Missing, unknown, unavailable, non-numeric, non-finite and out-of-range battery readings discard the
window. The next valid reading starts a new window without treating the gap as a charging jump.
An invalid battery reading yields no calculation; composite then follows its normal branch and
fallback rules. A negative net percentage change contributes no charging power.

Battery readings continue to populate the window while another composite branch is selected.
When the charging condition becomes false, its power contribution stops immediately. No pending
energy is added or compensated. A quick return to the charging branch reuses the recent valid
history; a restart or invalid reading clears it.

The smoothing window delays changes in estimated power. A longer window reduces fluctuations from
whole-percentage steps but increases startup lag and energy lost when a charge is interrupted.
A short charge can therefore have substantial relative energy error. Clamping large jumps can also
reduce counted energy. Assess total energy and instantaneous power separately when calibrating a
profile, and validate on charges that were not used to choose the coefficient.

See the [draft replay evaluation](../contributing/battery-rate-replay.md) for measured energy and power errors.
