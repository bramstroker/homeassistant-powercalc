# Troubleshooting measurements

This page covers common measure tool problems. For standby readings that show as `0` W, start with [Standby troubleshooting](standby_troubleshooting.md).

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
