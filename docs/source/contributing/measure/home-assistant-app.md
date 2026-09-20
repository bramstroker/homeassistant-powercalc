# Home Assistant app

The Powercalc Measure app is the recommended way to run measurements on Home Assistant OS (`amd64` and `aarch64`). Home Assistant Container and Core installations should use the [CLI](setup.md) instead.

The app guides you through configuring, running, and reviewing measurements. It uses Home Assistant entities to control devices and can read power from a Home Assistant sensor or directly from a Shelly, Kasa, or Tapo plug. Home Assistant supplies authentication and Core API access, so you do not create or paste a long-lived access token.

- [App settings](home-assistant-app/settings.md): power meters, connection checks, and developer options.
- [Results and sessions](home-assistant-app/sessions.md): GitHub contributions, resume, downloads, and backups.
- [Measurement automations](home-assistant-app/automations.md): notifications and flashing the measured lights.
- [App troubleshooting](home-assistant-app/troubleshooting.md): connection, calibration, and storage problems.

## Availability and installation

1. In Home Assistant, open **Settings > Apps > App store**.
2. Open the app-store repository menu and add `https://github.com/bramstroker/powercalc-measure-app`.
3. Find **Powercalc Measure**, select **Install**, and wait for the pre-built image to download.
4. Start the app and select **Open Web UI**. Optionally enable **Show in sidebar**.

No port, host networking, Home Assistant configuration mapping, or API credentials are required. App installation is not available on non-Supervisor installation types.

## Supported measurements

| Measurement | Home Assistant entity | Output |
| --- | --- | --- |
| Light | `light` | Brightness, color-temperature, HS, and effect LUT data with optional `model.json` |
| Smart speaker | `media_player` | Linear volume calibration and optional `model.json` |
| Fan | `fan` | Linear percentage calibration and optional `model.json` |
| Charging device | `vacuum` or `lawn_mower` | Battery-level charging calibration and optional `model.json` |
| Average | No controlled device required | Average power over a configured duration |
| Recorder | Optional tracked entities; guided vacuum and dock selection | Playbook CSV or entity-state recordings with experimental profile analysis |

See [App settings](home-assistant-app/settings.md) for supported power meters and connection checks.

Direct Hue, Tuya, Tasmota and myStrom controllers or meters, OCR, and manual power entry remain CLI-only.

## Measurement safety

!!! danger "The selected device is controlled automatically"

    A run may repeatedly change brightness, color, volume, or fan speed and can take hours. Charging measurements observe the device for an extended period. Do not use a safety-critical device. Avoid looking directly at high-output lights and take care with high speaker volume or moving equipment.

Keep people, automations, adaptive-lighting systems, and other controllers from changing the device during a run. Verify that the chosen power meter measures only the target load, and keep Home Assistant, the device, and the meter powered and reachable until completion.

## Running a measurement

1. Configure and test the measurement device in [Settings](home-assistant-app/settings.md).
2. Open **All sessions** and select **New measurement**.
3. Select a measurement type and the Home Assistant entity when that measurement controls a device.
4. Enter the profile details and measurement-specific options. Light measurements also let you choose the modes advertised by the selected entity. For loads too low for the meter, see [Measuring low-power devices](low-power-measurements.md).
5. Run the setup check and review its estimates, warnings, meter diagnostics, and timing settings. For lights without a dummy load, this checks representative low-load settings and standby, then leaves the lights off. Use **Recheck setup** after changing the physical setup. See [Measuring low-power devices](low-power-measurements.md) for check details and readings of `0` W.
6. Start the session. Complete the dummy-load calibration or reuse confirmation when enabled. Average, recorder, speaker, and charging measurements also pause for an explicit confirmation when the physical device must be prepared or the actual sampling period is about to begin.
7. Follow live progress, current operating values, recent power samples, and session logs. You can close or reload the browser; the app owns the job and restores its persisted status when you return.
8. Review plots and download generated CSV, model, or recording files from the result view. For generated profiles, follow [Results and sessions](home-assistant-app/sessions.md) to contribute through GitHub or download files for manual submission.

If standby could not be measured, the completed lookup tables are retained. See [Standby recovery](low-power-measurements.md#recover-a-completed-light-profile-with-unavailable-standby) to finish the profile without repeating the measurement.

The PowerCalc logo and the **All sessions** action in the top bar return to the session dashboard. Only one measurement runs at a time; while one is active, its dashboard entry provides the monitor action and starting or resuming another session is disabled.

### Recording a vacuum and dock

See [Recording a vacuum and dock](modes.md#recording-a-vacuum-and-dock) for entity selection, recording requirements, and experimental profile analysis.

## Measure session status sensor

Powercalc exposes the app's current session state through `sensor.measure_session_status`. See [Measurement automations](home-assistant-app/automations.md) for the sensor attributes and examples to notify your phone or flash the measured lights when a session completes.
