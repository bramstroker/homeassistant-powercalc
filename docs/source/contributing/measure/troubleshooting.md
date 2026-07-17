# Troubleshooting measurements

This page covers common measure tool problems. For standby readings that show as `0` W, start with [Standby power shows 0 W](#standby-power-shows-0-w).

## Readings stay at 0 W

Common causes:

- The power meter cannot measure the low load accurately.
- The wrong power sensor was selected.
- The measured device is not actually behind the selected power meter.
- The device turned off at very low brightness.
- Home Assistant has not received a fresh sensor update.

Try:

- Increase `MIN_BRIGHTNESS` for lights that do not stay on at brightness `1`.
- Use `POWER_METER=hass` with a known-good Home Assistant power sensor.
- Set `HASS_CALL_UPDATE_ENTITY_SERVICE=true` when using a Home Assistant power sensor.
- Increase `SLEEP_TIME` and `SLEEP_TIME_SAMPLE`.
- Use multiple identical lights in parallel or a dummy load when the load is below the meter accuracy threshold.

## Standby power shows 0 W

Some bulbs use very little standby power (often 0.1-0.3 W). Most consumer grade smart plugs have a minimum measurable load of 0.3-0.5 W. Anything below that is rounded down to zero, even though the bulb does consume standby power.

Try the following steps in order.

### Measure multiple bulbs in parallel

If you have more than one identical bulb, connect them in parallel and measure their combined standby power.

Example:

- Expected standby: ~0.2 W per bulb
- With 4 bulbs: ~0.8 W total, which is usually measurable

Make sure to have a group in Home Assistant that turns all bulbs on and off simultaneously during measurement. In the measure tool wizard select `yes` when asked `Are you measuring multiple lights?`, then enter the number of bulbs you are measuring.

### Add a dummy load

Some smart plugs require a stable resistive load before they can measure accurately. Use a small incandescent bulb (e.g., 25-40 W) as a dummy load on the same circuit. An oven bulb is a good choice since it uses little power and is easy to find.

!!! warning

    Do **not** use an LED bulb as a dummy load.
    LED bulbs are not stable resistive loads and will cause fluctuating or inaccurate readings.

The power meter must also provide voltage readings so the measure tool can calculate and subtract the dummy-load consumption. In the Home Assistant app, let the load warm up before starting its inline calibration. Calibration samples at least 20 periods of 30 seconds and continues if the calculated resistance is not stable. Keep the same dummy load connected for the entire measurement.

### Try a different smart plug or energy meter

Not all smart meters can measure sub-watt loads. If possible, try another brand or model known for decent low-load accuracy.

Examples:

- Good: many Tasmota-based plugs, Shelly Plug Gen3, Blitzwolf/Nous plugs
- Less accurate: older Shelly Plug S, many Tuya-based plugs below 0.5 W

### Standby is too low to measure

If none of the above methods help, the bulb's standby consumption is likely below the accuracy threshold of your meter. In that case the measurement tool cannot determine a reliable value.

You may manually set a fallback estimate (e.g., 0.2 W), but actual measurement is always preferred when possible. When doing this please note it in the PR description when submitting your measurements.

## Readings are stale or repeated

Some power meters do not publish a new value when the measured value barely changes. The light runner can briefly change the light to force a new meter reading and then remeasure the target state.

```env
MAX_NUDGES=3
PULSE_TIME_NUDGE=2
SLEEP_TIME_NUDGE=10
```

Use this only when you see stale readings. A better power meter update interval is usually preferable.

## Home Assistant entities do not appear

The tool filters entities by domain or unit:

- Power sensors must use unit `W`.
- Voltage sensors must use unit `V`.
- Fan mode lists `fan` entities.
- Smart speaker mode lists `media_player` entities.
- Charging mode lists `vacuum` or `lawn_mower` entities, depending on the selected device type.

If an entity is missing, check its Home Assistant state and attributes first. Also verify `HASS_URL` points to the API endpoint and `HASS_TOKEN` is a valid long-lived access token.

## Tuya power plug will not connect

For Tuya measuring devices, disable or remove the plug from other local integrations and reboot the plug. Some Tuya devices support only one local connection at a time.

## Shelly `KeyError: 'apower'`

Some Shelly devices do not expose the endpoint expected by the direct Shelly power meter integration.

Known affected devices include:

- Shelly EM Gen3 (`S3EM-002CXCEU`)

Use `POWER_METER=hass` for these devices and read the power value through Home Assistant instead.

## The session was interrupted

For light measurements, keep the partial CSV file and run the same mode again with:

```env
RESUME=true
```

The tool resumes after the last completed variation where possible. If you want a clean restart, delete the partial CSV file for that mode.

## Values look inconsistent

Check the measurement environment before editing output files:

- No automations should change the device during the run.
- The measured device should be the only changing load on the meter.
- The device should have enough time to settle after each command.
- The power meter should update more frequently than the sampling interval.
- The light should not be thermally throttling or changing behavior over time.

When in doubt, rerun a smaller mode such as `brightness` or use `Recorder` to inspect the power pattern over time.
