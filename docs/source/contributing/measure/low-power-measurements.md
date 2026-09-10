# Measuring low-power devices

Small lights and standby loads can consume less power than a consumer smart plug can resolve. A meter may round the
reading to `0` W even though the device is consuming power, or alternate between zero and a small value. Detecting
this before a long run prevents incomplete profiles.

## Check the measurement floor first

Confirm that the device is the only changing load behind the meter, then test its lowest expected operating point.
For a light, this can be brightness `1`, a color-temperature endpoint, or a saturated color that uses only one LED
channel. A nonzero white reading does not guarantee that every color channel remains measurable.

The Home Assistant app's **Check light and setup** action automates this check for deterministic light modes. It
briefly tests representative low-load points, uses the configured settle, sample, and retry settings, and leaves the
lights off. The review screen lists every checked point and its aggregate power. Dynamic effects are excluded because
a short sample cannot characterize their changing load.

The check covers the lowest points at which the light is *on*. It does not measure standby power, which the meter can
still round to `0` W even when every checked point reads a usable value. Verify the standby row of the generated CSV
afterwards, and apply the same approaches below when it is zero.

If any representative point repeatedly reads `0` W, use one of the approaches below before starting the measurement.

## Measure multiple identical devices together

Measuring several identical devices in parallel raises the aggregate load above the meter's measurement floor. For
example, four bulbs that each use approximately 0.2 W in standby produce a combined load of approximately 0.8 W.

In the Home Assistant app, enable **Measure multiple lights** and select up to three individual light entities. For
larger sets, prefer a native Zigbee or Hue group because it sends one lighting-network command. A
[Home Assistant light group](https://www.home-assistant.io/integrations/group/) also works but may send a separate
command to each member. Enter the total number of physical lights in **Number of lights**; Powercalc divides the
aggregate reading by that number.

Only combine devices when all of them:

- Are the same exact model.
- Receive the same operating-point commands.
- Are powered behind the same meter.
- Can be isolated from unrelated changing loads.

This is usually the best option when several identical devices are available because it does not require subtracting
another load from the measurement.

## Add a resistive dummy load

A stable resistive load connected in parallel can move the combined consumption into the meter's accurate range.
Powercalc calibrates the dummy load and subtracts its calculated consumption from subsequent readings.

!!! warning

    Mains wiring and hot incandescent lamps can cause electric shock, fire, or burns. Use a safe enclosed setup and
    do not construct or modify mains wiring unless you are qualified to do so.

Use a stable resistive load, such as a suitable incandescent lamp. Do not use an LED lamp or another electronically
controlled load: its consumption is not stable enough for reliable subtraction. The meter must also provide voltage
readings so Powercalc can account for voltage-dependent changes in the dummy load.

In the Home Assistant app:

1. Connect only the dummy load and allow it to warm up.
2. Enable **Use resistive dummy load** during measurement setup.
3. Calibrate it until Powercalc reports a stable resistance.
4. Connect the target device in parallel without disconnecting the dummy load.
5. Keep the same meter, load, and wiring in place for the complete measurement.

Reuse a stored calibration only after confirming that the same warmed-up load is connected. Recalibrate after changing
the load, meter, wiring, or whenever its stability is uncertain.

## Use a meter with better low-load resolution

Meter specifications and a displayed number of decimal places do not prove accuracy at sub-watt loads. Prefer a meter
that has been validated with loads near the range you intend to measure. Check that it:

- Reports stable, repeatable sub-watt values instead of rounding them to zero.
- Updates frequently enough after every operating-point change.
- Exposes fresh timestamps when read through Home Assistant.
- Provides voltage readings when a dummy load will be used.

Compare the meter against a known stable low load before committing to a long profile run. Hardware-specific
recommendations can be added here as reproducible test results become available.

## Exclude unmeasurable operating points only when appropriate

For lights, raising **Minimum brightness** can avoid a range where the light turns off or the meter cannot resolve its
load. This deliberately excludes those brightness levels from the measured grid, so use it only when that tradeoff is
acceptable for the profile. Powercalc does not automatically change this setting during preflight.

Do not invent a precise standby value from an unstable or zero reading. If the load remains below the available
meter's range, document any manual fallback estimate clearly in the pull request. A real measurement is preferred.

## Verify the setup before a long run

- Repeat low-load readings and confirm they remain nonzero.
- Confirm the meter updates after changing the device state.
- Check that automations cannot change the measured devices.
- Confirm the device count before Powercalc divides aggregate readings.
- Inspect the resulting CSV files for zeros, unexplained jumps, and repeated stale values.

See [Troubleshooting measurements](troubleshooting.md) when readings are stale, entities are missing, or the tool
reports another runtime error.
