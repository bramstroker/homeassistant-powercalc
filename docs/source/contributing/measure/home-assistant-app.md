# Home Assistant app

!!! note "New"

    The Powercalc Measure app is the recommended way to run measurements on Home Assistant OS (`amd64` and `aarch64`). It is new and under active development, so feedback is welcome. Home Assistant Container and Core installations should use the [CLI](setup.md) instead.

The app provides an ingress UI for configuring, validating, running, and reviewing Powercalc measurements. It uses Home Assistant entities to control devices and can read power from either a Home Assistant sensor or a Shelly plug. Home Assistant supplies authentication and Core API access, so you do not create or paste a long-lived access token.

## Availability and installation

1. In Home Assistant, open **Settings > Apps > App store**.
2. Open the app-store repository menu and add `https://github.com/bramstroker/powercalc-measure-app`.
3. Find **Powercalc Measure**, select **Install**, and wait for the pre-built image to download.
4. Start the app and select **Open Web UI**. Optionally enable **Show in sidebar**.

No port, host networking, Home Assistant configuration mapping, or API credentials are required. App installation is not available on non-Supervisor installation types.

## Current scope

| Measurement | Home Assistant entity | Output |
| --- | --- | --- |
| Light | `light` | Brightness, color-temperature, HS, and effect LUT data with optional `model.json` |
| Smart speaker | `media_player` | Linear volume calibration and optional `model.json` |
| Fan | `fan` | Linear percentage calibration and optional `model.json` |
| Charging device | `vacuum` or `lawn_mower` | Battery-level charging calibration and optional `model.json` |
| Average | No controlled device required | Average power over a configured duration |
| Recorder | No controlled device required | Power time-series CSV until the user stops the recording |

The app supports these power-meter types:

- a Home Assistant power sensor reporting `W`, with automatic association of an optional voltage sensor reporting `V`;
- a directly polled Shelly plug, selected through network discovery or entered by IP address;
- a synthetic test meter for development and UI testing only.

Direct Hue, Tuya, Kasa, Tasmota and myStrom controllers or meters, OCR, and manual power entry remain CLI-only.

## Measurement device setup

Configure the measurement device once from the app settings before creating a session. Select the power-meter type, choose or discover the sensor or Shelly plug, and enter a recognizable measurement-device name for generated profile metadata.

Use **Test connection** to sample the configured meter before starting a long run. For Home Assistant sensors, the app checks:

- whether readings can be retrieved;
- whether the sensor reports at least `0.1 W` resolution;
- how often the source reports a new reading;
- whether the update interval is suitable for reliable measurements.

An update interval of two seconds or faster is recommended. Intervals above five seconds, no observed updates, or insufficient precision are reported as poor measurement quality. Directly polled Shelly meters are checked for connectivity and a valid reading; Home Assistant reporting cadence does not apply to them.

## GitHub contribution setup

GitHub authentication can be configured in **Settings** before starting a measurement. Device login is the recommended option and requests `public_repo` plus `workflow` access. Workflow access lets the app create a clean contribution branch from the latest upstream commit when the user's fork contains older GitHub Actions files. A personal access token with equivalent repository and workflow access is available as a fallback. The settings page shows the connected GitHub account and provides a disconnect action.

The credential is stored separately in the app's private `/data` directory and is never included in session diagnostics. Home Assistant may include it in app backups. Disconnect locally and revoke the OAuth authorization or token in GitHub when it is no longer needed.

After a completed light, speaker, fan, or charging measurement, the result page can prepare a profile contribution. Review the manufacturer, model, exact file list, JSON, commit message, and pull-request text before explicitly creating the pull request. The app creates or reuses your fork and submits one device to the Powercalc `master` branch.

Manual contribution remains available at all times. You can still download every generated file and follow the contribution guide when GitHub is not configured, automatic contribution is unavailable, or an existing profile needs to be updated.

## Measurement safety

!!! danger "The selected device is controlled automatically"

    A run may repeatedly change brightness, color, volume, or fan speed and can take hours. Charging measurements observe the device for an extended period. Do not use a safety-critical device. Avoid looking directly at high-output lights and take care with high speaker volume or moving equipment.

Keep people, automations, adaptive-lighting systems, and other controllers from changing the device during a run. Verify that the chosen power meter measures only the target load, and keep Home Assistant, the device, and the meter powered and reachable until completion.

### Using a resistive dummy load

A resistive dummy load can raise a low device load into a range that the power meter measures accurately. The app supports this for light, speaker, fan, charging, average, and recorder measurements made with a real power meter.

!!! danger "Use only a safe, stable resistive load"

    Connect the dummy load in parallel with the measured device only when you understand the electrical and thermal safety implications. Use a stable resistive load, such as a suitable incandescent bulb. Do not use an LED bulb or another electronically controlled load. Keep the dummy load connected and powered for the entire calibration and measurement.

Dummy-load correction requires voltage readings. The selected Home Assistant power sensor must have an associated voltage sensor reporting `V`, or the Shelly meter must provide voltage. The synthetic test meter cannot be used for dummy-load measurements.

Before the first measurement, the app calibrates the resistance of the warmed-up dummy load:

1. Connect only the dummy load to the power meter and let it warm up.
2. Confirm that calibration can start. The app measures at least 20 periods of 30 seconds, so calibration takes at least 10 minutes.
3. If the resistance is still rising or falling, let the app continue until the reading is stable.
4. Connect the target device in parallel without disconnecting the dummy load, then confirm that measurement can start.

The app stores a successful calibration for that power meter. A later session can reuse it after you explicitly confirm that the same warmed-up load is connected, or you can choose **Recalibrate**. Recalibrate after changing the dummy load, power meter, or wiring, or whenever stability is uncertain.

During the actual run, live and saved power readings show the target device consumption after subtracting the calculated dummy-load contribution. A calibration interrupted before its resistance becomes stable is not saved.

## Running a measurement

1. Configure and test the measurement device in **Settings**.
2. Select a measurement type and the Home Assistant entity when that measurement controls a device.
3. Enter the profile details and measurement-specific options. Light measurements also let you choose the modes advertised by the selected entity. Enable a resistive dummy load only when the device load would otherwise be too low for the meter.
4. Review preflight estimates, warnings, meter diagnostics, and advanced timing settings.
5. Start the session. Complete the dummy-load calibration or reuse confirmation when enabled. Average, recorder, speaker, and charging measurements also pause for an explicit confirmation when the physical device must be prepared or the actual sampling period is about to begin.
6. Follow live progress, current operating values, recent power samples, and session logs. You can close or reload the browser; the app owns the job and restores its persisted status when you return.
7. Review plots and download generated CSV, model, or recording files from the result view. For generated profiles, either prepare a GitHub pull request in the app or use the permanent manual-contribution option.

Only one measurement runs at a time.

## Cancellation and resume

Cancellation is cooperative. A device request or configured wait already in progress may finish before the app stops changing the device. The app keeps complete output rows and does not mark partial output as completed.

Light LUT measurements can resume compatible partial output. Resume with the same light, meter, modes, and measurement settings. Other measurement types currently start a new session after interruption. If the UI does not offer resume, start over rather than manually editing session files.

## Storage and backups

Requests, session state, events, and output are stored in the app's private `/data` directory. Home Assistant includes this directory in app backups. The app does not mount or write to the Home Assistant configuration directory.

Persisted GitHub credentials are also stored under `/data`, separately from preferences, sessions, and diagnostics. Treat app backups as sensitive while a GitHub account is connected.

The result view provides:

- raw measurement and generated model files;
- interactive plots for supported output;
- high-resolution plot image downloads;
- a diagnostics download containing the session snapshot, request, events, logs, and file inventory for issue reports.

Entity IDs remain present in diagnostics because they are useful when troubleshooting entity selection and state updates. Download files through the authenticated ingress result view before removing the app or deleting its data.

## Developer options

Two options exist to exercise the measurement flow without physical hardware. Profiles produced with either are meaningless; keep both off for normal use.

- **Synthetic test meter**: select it under **Settings → Power meter** to replace the real power sensor with a generated reading. It is separate from the calibrated resistive dummy-load feature and cannot be used to calibrate one.
- **Developer mode**: enable it in the app's **Configuration** tab and restart the app to show a **Use virtual device** toggle on the light, speaker, charging, and fan setup forms. The toggle replaces the selected Home Assistant entity with a virtual (dummy) controller. Combine it with the synthetic test meter for a fully simulated run. When running the app outside the add-on, pass `--developer-mode` on the command line instead.

## Troubleshooting

### A device or sensor is not listed

Confirm that the entity is available in Home Assistant and belongs to the required domain for the selected measurement. Power sensors must report `W`; optional voltage sensors must report `V`. Correct the source integration or unit, then reload the app.

### Power-meter validation warns about quality

Watch the sensor in Home Assistant Developer Tools while changing the load. The source should expose at least one decimal place and publish a new reading every two seconds or faster where possible. Increase the source integration's update rate or use a faster meter before starting the full measurement.

### Dummy-load calibration is unavailable or unstable

Confirm that the configured meter provides voltage readings. Home Assistant voltage sensors must report `V`; a Shelly must expose voltage through its meter API. The synthetic test meter does not support calibration.

If resistance does not stabilize, allow the load to warm up longer and ensure no other load behind the meter is changing. Recalibrate after correcting the setup. Do not continue with a stored calibration when the physical load, meter, or wiring has changed.

### Shelly discovery does not find the plug

Confirm that Home Assistant and the Shelly are on a network where mDNS discovery is available. IPv6-only and non-private addresses are not accepted. You can enter the device's private IPv4 address manually when discovery is unavailable.

### Ingress disconnected

Reload the app. Browser and ingress connections do not control the worker, and the UI restores the authoritative session snapshot. Review app logs if reconnecting continues to fail.

### An interrupted run cannot resume

Resume is rejected when output is incomplete or settings that determine the measurement sequence changed. Preserve the existing files for diagnosis, then start a new session with overwrite when appropriate.

### Storage errors

Check free disk space and the app log, then restart the app. Do not remove files from app data while a measurement is active. Restore the app data from a Home Assistant backup if needed.

### Reporting a problem

Enable debug logging in the app configuration and restart the app before reproducing the issue. After the session, download its diagnostics from the result view and attach that file to the issue together with the app log. Disable debug logging again after collecting the information.
