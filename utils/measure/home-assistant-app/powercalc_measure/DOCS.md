# Powercalc Measure

Powercalc Measure creates a light power profile using entities already available in Home Assistant. The app is experimental and supports Home Assistant OS on `amd64` and `aarch64` only.

## Before starting

The app repeatedly changes the selected light and may run for hours. Keep the light powered, do not rely on it for safety-critical illumination, and avoid automations or people changing it during a measurement. Confirm that the selected power sensor reports only the load being measured.

The first release supports:

- a Home Assistant `light` entity;
- a power sensor measured in watts;
- an optional voltage sensor measured in volts;
- brightness, color-temperature, HS, and supported combined light modes.

Direct Hue, Shelly, Tuya, Kasa, Tasmota and myStrom connections, OCR/manual meters, dummy loads, and non-light runners remain available only in the CLI.

## Installation

When the experimental Powercalc Apps repository is published:

1. Open **Settings > Apps > App store** in Home Assistant.
2. Add the published Powercalc Apps repository URL from the app-store repository menu.
3. Select **Powercalc Measure**, install it, and wait for the pre-built image to download.
4. Start the app and select **Open Web UI**.

The app requires Home Assistant OS. It cannot be installed on Home Assistant Container or Core installations; use the standalone measure Docker image there instead.

## Use

1. Start the app and enable **Show in sidebar** if desired.
2. Select **Open Web UI**.
3. Choose the light and its power sensor. Add a voltage sensor only when your setup needs it.
4. Review preflight warnings and settings before starting.
5. Leave Home Assistant and the measured devices running. Closing or reloading the browser does not stop an active measurement.
6. Download the generated CSV and model files from the result view.

Home Assistant authenticates ingress and provides Core API access. Do not configure or paste a long-lived token into the app.

## Sessions, cancellation, and storage

Only one measurement can run at a time. **Cancel** requests a cooperative stop, so an in-flight device call or wait may finish first. Completed CSV rows are retained and may be resumable when the same measurement settings are used.

Session state and output are stored in the app's private `/data` directory. Home Assistant includes this data in app backups. Use the result view to download files; no Home Assistant configuration directory is mounted into the app.

After an app or host restart, reopen the UI. An interrupted session is shown as resumable only when its stored output passes compatibility checks; otherwise it is reported as failed rather than incorrectly completed.

## Troubleshooting

### An entity is missing

Confirm that the light or sensor exists and is currently available in Home Assistant. Power sensors must use `W`, and voltage sensors must use `V`. Refresh the app after correcting the entity or its unit.

### Power readings are stale

Check the source integration's update interval and verify that the value changes in Home Assistant Developer Tools while the load changes. A stale meter cannot produce a trustworthy profile.

### The UI disconnected

Ingress or browser reconnects do not own the measurement job. Reload the app to restore the persisted session snapshot. Check the app log if reconnecting repeatedly fails.

### A session was interrupted

Use **Resume** only when the UI offers it and the light, meter, and measurement settings are unchanged. Otherwise start a new measurement and choose overwrite when prompted.

### Storage failed

Check available disk space in Home Assistant, then restart the app. Do not delete app data while a job is active. Restore an app backup if persistent state was damaged.

For additional guidance, see the [Powercalc measure documentation](https://docs.powercalc.nl/contributing/measure/home-assistant-app/).
