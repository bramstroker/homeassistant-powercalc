# Powercalc Measure

Powercalc Measure creates device power profiles using entities already available in Home Assistant. The app is experimental and supports Home Assistant OS on `amd64` and `aarch64` only.

## Before starting

The app repeatedly changes the selected device and may run for hours. Keep the device powered, do not rely on it for safety-critical purposes during the run, and avoid automations or people changing it during a measurement. Confirm that the selected power sensor reports only the load being measured.

The app currently supports:

- light profiles from a Home Assistant `light` entity, covering brightness, color-temperature, HS, and supported combined light modes;
- speaker, fan, and charging (robot vacuum and robot lawn mower) measurements through their Home Assistant entities;
- average and recorder measurements for any load;
- power readings from a Home Assistant power sensor in watts (with an optional voltage sensor in volts) or a Shelly plug;
- calibrated resistive dummy-load correction for every real measurement type when the meter provides voltage readings.

Direct Hue, Tuya, Kasa, Tasmota and myStrom connections, OCR, and manual power meters remain available only in the CLI.

## Installation

1. Open **Settings > Apps > App store** in Home Assistant.
2. Add the Powercalc Apps repository from the app-store repository menu: `https://github.com/bramstroker/powercalc-measure-app`.
3. Select **Powercalc Measure**, install it, and wait for the pre-built image to download.
4. Start the app and select **Open Web UI**.

The app requires Home Assistant OS. It cannot be installed on Home Assistant Container or Core installations; use the standalone measure Docker image there instead.

## Use

1. Start the app and enable **Show in sidebar** if desired.
2. Select **Open Web UI**.
3. Choose the measurement type, the device entity, and its power sensor. Add a voltage sensor only when your setup needs it.
4. Review setup check warnings and settings before starting.
5. Leave Home Assistant and the measured devices running. Closing or reloading the browser does not stop an active measurement.
6. Download the generated CSV and model files from the result view.

Home Assistant authenticates ingress and provides Core API access. Do not configure or paste a long-lived token into the app.

### Measurement defaults

Open **Settings** in the app to configure the measurement device and reusable tuning defaults. Choose a Home Assistant power sensor or discover or manually configure a Shelly plug, enter a recognizable measurement-device name, and use **Test connection** before starting a long run.

For Home Assistant sensors, the connection test checks that readings are available, have at least `0.1 W` resolution, and update frequently enough. Two seconds or faster is recommended; more than five seconds is considered unsuitable for reliable automated measurements.

### GitHub contribution

You can connect GitHub from the app's global **Settings** before measuring. Device login is recommended and requests public-repository plus workflow access so a contribution can be based on the latest upstream commit even when your fork is stale. A personal access token with equivalent access is available as a fallback. The connection is reused for later contributions until you disconnect it.

After a completed light, speaker, fan, or charging measurement, the result page can prepare an automatic contribution. Review the manufacturer, model, exact files, generated JSON, commit message, and pull-request text before creating the pull request. The app creates or reuses your fork and submits one device to Powercalc.

Manual contribution is always available. You can download the generated files and follow the contribution guide even when GitHub is disconnected, automatic submission fails, or the profile already exists.

### Resistive dummy loads

Use a resistive dummy load when the target device consumes too little power for the configured meter to measure accurately. The feature requires the selected Home Assistant power sensor to have an associated voltage sensor reporting `V`, or a Shelly meter with voltage support. It is not available with the synthetic test meter.

Use only a safe, stable resistive load, such as a suitable incandescent bulb. Do not use an LED bulb or another electronically controlled load. Connect the load in parallel only when you understand the electrical and thermal safety implications, and keep it connected throughout calibration and measurement.

For a new calibration, warm up the load and connect only that load to the meter. The app measures at least 20 periods of 30 seconds and continues when the calculated resistance is still changing. After calibration, connect the target device in parallel and confirm before measurement starts.

A later session can reuse the stored calibration only after you explicitly confirm that the same warmed-up load is connected. Choose **Recalibrate** whenever the load, meter, or wiring changes or stability is uncertain. Live and saved readings show the target-device power after the calculated dummy-load contribution is removed.

## Sessions, cancellation, and storage

Only one measurement can run at a time. **Cancel** requests a cooperative stop, so an in-flight device call or wait may finish first. Completed CSV rows are retained and may be resumable when the same measurement settings are used.

Session state, output, and any persisted GitHub credential are stored in the app's private `/data` directory. Home Assistant includes this data in app backups. GitHub credentials are kept separate from settings, sessions, and diagnostics. The result view shows plots for supported measurement output and lets you download raw files, individual plot images, and a session diagnostics bundle containing the request, snapshot, events, logs, and file inventory. No Home Assistant configuration directory is mounted into the app.

After an app or host restart, reopen the UI. An interrupted session is shown as resumable only when its stored output passes compatibility checks; otherwise it is reported as failed rather than incorrectly completed.

## Troubleshooting

### An entity is missing

Confirm that the device entity or sensor exists and is currently available in Home Assistant. Power sensors must use `W`, and voltage sensors must use `V`. Refresh the app after correcting the entity or its unit.

### Power readings are stale

Check the source integration's update interval and verify that the value changes in Home Assistant Developer Tools while the load changes. The sensor should expose at least one decimal place and preferably update every two seconds or faster. A stale or low-resolution meter cannot produce a trustworthy profile.

### The UI disconnected

Ingress or browser reconnects do not own the measurement job. Reload the app to restore the persisted session snapshot. Check the app log if reconnecting repeatedly fails.

### A session was interrupted

Use **Resume** only when the UI offers it and the device, meter, and measurement settings are unchanged. Otherwise start a new measurement and choose overwrite when prompted.

### Storage failed

Check available disk space in Home Assistant, then restart the app. Do not delete app data while a job is active. Restore an app backup if persistent state was damaged.

### Enabling debug logging

Turn on **Debug logging** in the app's **Configuration** tab and restart the app to capture verbose output in the app log. Use it when reporting an issue, then turn it back off once you have collected the log.

### Synthetic test meter (developers)

The **Synthetic test meter** type under **Settings → Power meter** replaces the real power sensor with a generated reading. It exists only to exercise the measurement flow without a physical load, so any profile produced while it is enabled is meaningless. It is separate from the calibrated resistive dummy-load feature and cannot be used to calibrate one. Keep the type set to a real power meter for actual measurements.

### Developer mode (virtual devices)

Turn on **Developer mode** in the app's **Configuration** tab and restart the app to show a **Use virtual device** toggle on the light, speaker, charging, and fan setup forms. The toggle replaces the selected Home Assistant entity with a virtual (dummy) controller so the whole measurement flow can be tested without controlling a real device. Combine it with the synthetic test meter for a fully simulated run. Profiles produced this way are meaningless; leave developer mode off for normal use. When running the app outside the add-on, pass `--developer-mode` on the command line instead.

For additional guidance, see the [Powercalc measure documentation](https://docs.powercalc.nl/contributing/measure/home-assistant-app/).
