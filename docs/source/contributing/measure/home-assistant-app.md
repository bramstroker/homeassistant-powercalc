# Home Assistant app

!!! warning "Experimental"

    The Powercalc Measure app is under active development. It is intended for Home Assistant OS on `amd64` and `aarch64`; Home Assistant Container and Core installations should continue using the [Docker or native setup](setup.md).

The app provides an ingress UI for creating light profiles from entities already available in Home Assistant. Home Assistant supplies authentication and Core API access, so you do not create or paste a long-lived access token.

## Availability and installation

The app repository metadata is currently staged with the Powercalc source while the first experimental image is validated. When the dedicated Powercalc app repository is published:

1. In Home Assistant, open **Settings > Apps > App store**.
2. Open the app-store repository menu and add the published Powercalc Apps repository URL.
3. Find **Powercalc Measure**, select **Install**, and wait for the pre-built image to download.
4. Start the app and select **Open Web UI**. Optionally enable **Show in sidebar**.

No port, host networking, Home Assistant configuration mapping, or API credentials are required. App installation is not available on non-Supervisor installation types.

For development on a Home Assistant OS host, copy `utils/measure/home-assistant-app/powercalc_measure` into `/addons/powercalc_measure` and reload the app store. The image version referenced by the copied metadata must already be published; source image builds run from this repository's `ha-app` Docker target.

## MVP scope

The first release supports:

- Home Assistant light entities;
- Home Assistant power sensors using `W`;
- optional Home Assistant voltage sensors using `V`;
- brightness, color-temperature, HS, and supported combined light measurements;
- preflight validation, live progress, reconnect, cancellation, resume, and file downloads.

The CLI remains the supported path for direct Hue, Shelly, Tuya, Kasa, Tasmota or myStrom connections; OCR and manual meters; dummy loads; and speaker, fan, charging, recorder, or average runners.

## Measurement safety

!!! danger "The selected light is controlled automatically"

    A run repeatedly changes brightness and color and may take hours. Do not use a safety-critical light, and avoid looking directly at high-output lights. Keep people, automations, and adaptive-lighting systems from changing the light during the run.

Verify that the chosen power sensor measures only the target light. Keep Home Assistant, the light, and the meter powered and reachable until completion.

## Running a measurement

1. Open the app and select the light, power sensor, and optional voltage sensor.
2. Choose supported measurement modes and enter the device details.
3. Review the setup check results. Resolve unavailable entities, incompatible units, or storage errors before continuing.
4. Start the measurement. You can close or reload the browser; the app owns the job and restores its latest persisted status when you return.
5. Download generated CSV and model files from the result view.

Only one measurement runs at a time.

## Cancellation and resume

Cancellation is cooperative. A device request or configured wait already in progress may finish before the app stops changing the light. The app keeps complete CSV rows and does not mark partial output as completed.

App and host restarts classify interrupted sessions as resumable only when the persisted request and output remain compatible. Resume with the same light, meter, and settings. If the UI does not offer resume, start over rather than manually editing session files.

## Storage and backups

Requests, session state, events, and output are stored in the app's private `/data` directory. Home Assistant includes this directory in app backups. The app does not mount or write to the Home Assistant configuration directory.

Download files through the authenticated ingress result view before removing the app or deleting its data.

## Troubleshooting

### A light or sensor is not listed

Confirm that the entity is available in Home Assistant. Power sensors must report `W`; optional voltage sensors must report `V`. Correct the source integration or unit, then reload the app.

### Readings do not follow the light

Watch the sensor in Home Assistant Developer Tools while changing the light. Increase the source integration's update rate if readings are stale, and ensure no unrelated load is included.

### Ingress disconnected

Reload the app. Browser and ingress connections do not control the worker, and the UI restores the authoritative session snapshot. Review app logs if reconnecting continues to fail.

### An interrupted run cannot resume

Resume is rejected when output is incomplete or settings that determine the measurement sequence changed. Preserve the existing files for diagnosis, then start a new session with overwrite when appropriate.

### Storage errors

Check free disk space and the app log, then restart the app. Do not remove files from app data while a measurement is active. Restore the app data from a Home Assistant backup if needed.
