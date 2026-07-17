# Measure tool

!!! warning

    Incorrect use of electrical and measuring devices carries a risk of electric shock. It can cause serious injury or death.

Powercalc profiles are based on real measurements. The measure tool automates the repetitive parts: it controls the device, reads a power meter, stores the measured values, and can generate the first version of `model.json`.

Use this guide when you want to create a new power profile for the library or when you want to measure a device for your own installation.

## What the tool can measure

| Mode | Use for | Result |
| --- | --- | --- |
| Light bulb(s) | Lights with brightness, color temperature, color, white, or effects support | LUT CSV files and optional `model.json` |
| Smart speaker | Media players where power changes with volume or playing state | Linear calibration and optional `model.json` |
| Fan | Fans with percentage control | Linear calibration and optional `model.json` |
| Charging device | Vacuum robots and lawn mower robots while charging | Linear calibration and optional `model.json` |
| Average | Any device where you only need an average power value | Average power reading |
| Recorder | Capturing power patterns for the [Playbook strategy](../../strategies/playbook.md) | Time series CSV |

The light mode is the most common contribution path. Other modes are useful when a device has a predictable relation between an entity attribute and power consumption.

## Recommended reading path

1. [Setup](setup.md) - choose the Home Assistant app, Docker, or native installation.
2. [Home Assistant app](home-assistant-app.md) - use the guided UI for lights, speakers, fans, charging devices, averages, and recordings.
3. [Light profiles](lights.md) - create LUT profiles for lights.
4. [Other measure modes](modes.md) - measure speakers, fans, charging devices, average readings, or recorder sessions.
5. [Output and pull requests](output.md) - inspect the generated files and submit them.
6. [Troubleshooting](troubleshooting.md) - fix common measurement problems.
7. [Architecture](architecture.md) - understand how the CLI and app share the request, assembly, execution, and result pipeline.

For OCR-based meters, also see [Measure using OCR](measure-ocr.md).

## Contribution requirements

!!! important

    Devices must have a unique and specific model identification. Generic model identifiers that can represent many different products are not acceptable for the shared library. A common example is a light identifying only as `TS0505B`.

Before spending time on a long measurement session, check that the device can be identified precisely:

- Use the real manufacturer and exact model where possible.
- Avoid profiles for generic white-label devices when the same identifier may refer to different hardware.
- Add the full product name as an alias when the model directory uses only the model ID.

When the device is not suitable for the public library, you can still use the generated files as a custom profile in your own Home Assistant installation.

## Safety and measurement quality

- Use a power meter that can measure low loads accurately. For small lights, sub-watt accuracy matters.
- Let devices and power meters settle before trusting readings.
- Pause Home Assistant automations that might change the measured device during a run.
- Keep the measured device as the only changing load behind the power meter, unless you deliberately use a dummy load.
- If readings are noisy, increase sample count or waiting times instead of editing the generated CSV by hand.

The tool helps with automation, but it cannot compensate for an inaccurate meter, unstable device behavior, or another automation changing the device state during measurement.
