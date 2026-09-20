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

After the on-state checks, the app turns the lights off, waits for the configured standby settling time, and checks
standby using the same sampling and stale-reading recovery settings as the final measurement. The review screen
shows standby watts **per light**, or a nonblocking warning when it cannot be measured reliably. You can still start
the measurement after that warning. Standby is measured again at the end of the run.

Use **Recheck setup** after changing the physical setup; it bypasses the short-lived result cache. Starting an
unchanged measurement shortly after checking it reuses the cached check. The active light check, including standby,
is skipped when a dummy load is configured, when using dummy adapters, or when measuring only dynamic effects.

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

The app supports dummy-load correction for light, speaker, fan, charging, average, and recorder measurements
with a real power meter. A Home Assistant power sensor needs an associated voltage sensor reporting `V`; directly
polled Shelly, Kasa, and Tapo meters must expose voltage through their API. The synthetic test meter cannot be used.

In the Home Assistant app:

1. Connect only the dummy load and allow it to warm up.
2. Enable **Use resistive dummy load** during measurement setup.
3. Confirm calibration and wait until Powercalc reports a stable resistance. Calibration measures at least 20 periods of 30 seconds (at least 10 minutes); let it continue if resistance is still rising or falling.
4. Connect the target device in parallel without disconnecting the dummy load.
5. Keep the same meter, load, and wiring in place for the complete measurement.

Reuse a stored calibration only after confirming that the same warmed-up load is connected. Recalibrate after changing
the load, meter, wiring, or whenever its stability is uncertain. Choose **Recalibrate** to replace a stored calibration.
A calibration interrupted before resistance stabilizes is not saved. During the measurement, live and saved power
readings show the target device consumption after subtracting the calculated dummy-load contribution.

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

## Recover a completed light profile with unavailable standby

Exhausted zero or stale standby readings no longer discard a completed light measurement. The session retains its
lookup tables and reports that standby is unavailable; its raw `model.json` omits standby rather than recording zero
as a measured value. Connection, calibration, and other operational errors still need to be resolved.

In **Prepare profile**, enter **Standby power (W per light)** from a separate reliable measurement, or explicitly
choose **Use estimated standby**. The value must be finite and at least `0.05` W. Do not divide an entered value again
when several lights were measured together. Keep **Estimated** checked for estimates, or clear it when replacing an
estimate with a measured value. This also works for older completed sessions whose standby is missing or zero; no
new LUT run is required.

**Measure standby** retries only the standby reading. For light sessions, its setup dialog starts with the original
device settings and lets you change the controlled light entities, bulb count, standby settling time, and sampling settings.
The retry defaults to 10 seconds of settling and five samples with two seconds between readings. The dialog shows
progress, elapsed time, and the result; choose **Measure again** to revisit the setup or **Done** to close it.
Home Assistant meters also allow changing the power and voltage sensors. These changes apply only to the retry;
the completed session's configuration and LUT measurements are preserved.

You can remove the dummy load, reuse the original or a compatible saved calibration, or calibrate a new resistive
load. For a new calibration, preheat the dummy load until stable and disconnect the measured bulbs so only the dummy
load is connected to the meter. Choose **Calibrate dummy load**, then reconnect the bulbs in parallel after calibration
completes. Calibration continues if you close the dialog, disconnect, or reload the page. Reopen the same session’s standby dialog to check progress or cancel calibration. Stopping the app cancels an unfinished calibration. Keep the same warmed-up dummy load connected during standby measurement. Voltage support and calibration
compatibility are checked before measurement. The result subtracts the dummy load and divides by the retry's bulb count.

Confirm the selected devices and meter are connected correctly. Lights, speakers, and fans use their existing turn-off
routines; for charging and recorded devices, put the device into standby yourself before confirming. Lights may briefly
pulse on and off to refresh stale readings. A successful reading fills the field and clears **Estimated**, and its
effective setup and calibration are recorded separately in the session's `standby_retry.json`. If saving this optional
record fails, the measured value is still returned and the storage error is logged. Cancelling the setup,
an unavailable reading, or an error leaves your standby entry and completed measurements unchanged. Dummy meters and
controllers are allowed for testing, with a simulation notice; their results must not be submitted as real measurements.

The standby field, **Estimated** checkbox, and retry action are also available for non-light profiles. Their value
is watts for the device, not watts per light. Leave the optional field blank to preserve an existing value or
template. Library suggestions and the `0.4` W fallback apply only to lights.

The suggestion uses the median standby of at least three distinct, non-estimated light profiles with exactly the
same connectivity set and manufacturer (including manufacturer aliases). If too few match that manufacturer, it
uses at least three matching profiles across manufacturers. With too few comparable profiles, unknown connectivity,
or an unavailable library, it falls back to `0.4` W. The UI shows the basis and sample count. Changing manufacturer or
connectivity refreshes the suggestion but never replaces your entry automatically.

Validate the correction before submitting. The prepared preview, downloaded ZIP, and GitHub submission use the same
corrected value and estimated flag; estimates are also identified in the pull request. Original measurement artifacts
remain unchanged. A real measurement is preferred over any estimate.

## Verify the setup before a long run

- Repeat low-load readings and confirm they remain nonzero.
- Confirm the meter updates after changing the device state.
- Check that automations cannot change the measured devices.
- Confirm the device count before Powercalc divides aggregate readings.
- Inspect the resulting CSV files for zeros, unexplained jumps, and repeated stale values.

See [Troubleshooting measurements](troubleshooting.md) when readings are stale, entities are missing, or the tool
reports another runtime error.
