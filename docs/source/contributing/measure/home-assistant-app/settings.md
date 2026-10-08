# App settings

The app supports these power-meter types:

- a Home Assistant power sensor reporting `W`, with automatic association of an optional voltage sensor reporting `V`;
- a directly polled Shelly plug, selected through network discovery or entered by IP address;
- a directly polled Kasa or Tapo plug with energy monitoring, entered by IP address. Newer devices require the TP-Link account used to set them up;
- a synthetic test meter for development and UI testing only.

## Measurement device setup

Configure the measurement device once from the app settings before creating a session. Select the power-meter type, choose or discover the sensor or plug, and choose the meter name used by existing Powercalc profiles. The app loads these canonical names from the published library. You can still type a name when your meter is not listed or the library is temporarily unavailable.

Use **Test connection** to sample the configured meter before starting a long run. For Home Assistant sensors, the app checks:

- whether readings can be retrieved;
- whether the sensor reports at least `0.1 W` resolution;
- how often the source reports a new reading;
- whether the update interval is suitable for reliable measurements.

An update interval of two seconds or faster is recommended. Intervals above five seconds, no observed updates, or insufficient precision are reported as poor measurement quality. Directly polled Shelly, Kasa, and Tapo meters are checked for connectivity and a valid reading; Home Assistant reporting cadence does not apply to them.

## Using a resistive dummy load

For devices below the meter's measurement floor, see [Measuring low-power devices](../low-power-measurements.md#add-a-resistive-dummy-load) for voltage requirements, calibration, and reuse of a stored calibration.

## Developer options

Two options exist to exercise the measurement flow without physical hardware. Profiles produced with either are meaningless; keep both off for normal use.

- **Synthetic test meter**: select it under **Settings → Power meter** to replace the real power sensor with a generated reading. It is separate from the calibrated resistive dummy-load feature and cannot be used to calibrate one.
- **Developer mode**: enable it in the app's **Configuration** tab and restart the app to show a **Use virtual device** toggle on the light, speaker, charging, and fan setup forms. The toggle replaces the selected Home Assistant entity with a virtual (dummy) controller. Combine it with the synthetic test meter for a fully simulated run. When running the app outside the add-on, pass `--developer-mode` on the command line instead.
