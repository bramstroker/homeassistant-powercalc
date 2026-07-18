# CLI (Docker / native Python)

This page covers running the measure tool from the command line, either with Docker or natively with Python.

!!! tip

    On Home Assistant OS, the [Home Assistant app](home-assistant-app.md) is the recommended way to run measurements. Use the CLI when you run Home Assistant Container or Core, need a direct device power meter or Hue controller, use an OCR meter or manual readings, or develop the tool itself.

## Prepare a working directory

Create a separate directory for your measurement work, for example `powercalc-measure`. Copy `utils/measure/.env.dist` from the Powercalc repository into that directory and rename it to `.env`.

The working directory will contain:

- `.env` - your local configuration and credentials.
- `export/` - generated measurement files.
- `.persistent/` - resume data and cached dummy load measurements.

Do not commit your `.env` file. It can contain Home Assistant tokens or device keys.

## Docker

Install [Docker](https://docs.docker.com/get-docker/) and verify it is running:

```bash
docker version
```

Run the tool from the directory that contains `.env`.

=== "Linux and macOS"

    ```bash
    docker run --pull=always --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure-cli:latest
    ```

=== "Windows command prompt"

    ```bat
    docker run --pull=always --rm --name=measure --env-file=.env -v %CD%/export:/app/export -v %CD%/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure-cli:latest
    ```

When using PowerShell, use full absolute paths for the mounted directories.

## Native Python

Use the native setup when Docker does not work for you or when you are developing the measure tool itself.

Prerequisites:

- Python 3.14 or newer.
- `uv`, installed with `curl -LsSf https://astral.sh/uv/install.sh | sh` or another method from the uv documentation.

From the repository:

```bash
cd utils/measure
uv venv
uv sync --extra cli
uv run --extra cli python -m measure.measure
```

Native runs write output to `utils/measure/export`.

## Required configuration

At minimum, choose a power meter and the controller for the kind of device you measure.

```env
POWER_METER=hass
LIGHT_CONTROLLER=hass
MEDIA_CONTROLLER=hass
FAN_CONTROLLER=hass
CHARGING_CONTROLLER=hass
```

Supported power meters:

| `POWER_METER` | When to use |
| --- | --- |
| `hass` | Recommended general option. Reads a Home Assistant power sensor. |
| `shelly` | Reads directly from a Shelly device API. |
| `tasmota` | Reads directly from a Tasmota device. |
| `tuya` | Reads directly from a Tuya plug. |
| `kasa` | Reads directly from a TP-Link Kasa plug. |
| `mystrom` | Reads directly from a myStrom plug. |
| `manual` | Prompts you to enter readings manually. |
| `ocr` | Reads a meter display through OCR. See [OCR power meter](#ocr-power-meter). |

The `hass` power meter is often the easiest and most reliable path because it can use any power sensor Home Assistant already exposes.

## Home Assistant configuration

For `POWER_METER=hass` or any `hass` controller, set:

```env
HASS_URL=ws://homeassistant.local:8123/api/websocket
HASS_TOKEN=your_long_lived_access_token
```

The tool uses the Home Assistant WebSocket API. Older REST-style URLs (e.g. `http://homeassistant.local:8123/api`) are automatically normalized to the WebSocket endpoint, so existing configurations keep working.

For the power meter, the tool asks you to select a power sensor with unit `W`. When voltage readings are needed, it can also use a voltage sensor with unit `V`.

Set this when your power sensor does not update frequently enough:

```env
HASS_CALL_UPDATE_ENTITY_SERVICE=true
```

## Direct power meter configuration

Set only the variables needed by your selected `POWER_METER`.

```env
SHELLY_IP=x.x.x.x
SHELLY_TIMEOUT=60

TASMOTA_DEVICE_IP=x.x.x.x

KASA_DEVICE_IP=x.x.x.x

MYSTROM_DEVICE_IP=x.x.x.x

TUYA_DEVICE_ID=aaaaaaaaad89682385bbb
TUYA_DEVICE_IP=x.x.x.x
TUYA_DEVICE_KEY=aaaaaaaae1b8abb
TUYA_DEVICE_VERSION=3.3
```

For Tuya measuring devices, make sure no other integration is connected to the same device while measuring. Some Tuya plugs only allow one local connection at a time.

## OCR power meter

With `POWER_METER=ocr`, the tool reads power values from a camera pointed at the display of a power meter. This requires the native Python setup.

1. Install [tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) for your OS.
2. Install the optional OCR dependencies:

    ```bash
    cd utils/measure
    uv sync --extra cli --extra ocr
    ```

3. Start the OCR stream, passing the location of the tesseract executable:

    ```bash
    uv run --extra ocr python measure/ocr/main.py -t '/opt/homebrew/bin/tesseract'
    ```

4. Set `POWER_METER=ocr` in your `.env` and run the measure tool as usual in a second terminal.

The OCR method is tested with the Zhurui PR10 power meter. Other meters with a clearly readable display may also work.

## Predefining wizard answers

The tool normally asks questions in an interactive wizard. You can skip questions by defining the matching uppercase key in `.env`.

Common examples:

```env
SELECTED_MEASURE_TYPE=Light bulb(s)
MODE=color_temp
GENERATE_MODEL_JSON=true
GZIP=true
ENTITY_ID=light.example
MEASURE_DEVICE=Shelly Plug S
MODEL_ID=LED1837R5
MODEL_NAME=Example Light E27
RESUME=true
```

This is useful when you need to rerun one color mode or resume after an interrupted session.

## Timing and sampling

The default timings work for many devices, but you can tune them when the meter updates slowly or the device needs more time to settle.

```env
SLEEP_TIME=3
SLEEP_TIME_SAMPLE=3
SAMPLE_COUNT=2
SLEEP_INITIAL=10
SLEEP_STANDBY=20
```

Use a higher `SAMPLE_COUNT` to reduce noise. Increase `SLEEP_TIME` or `SLEEP_TIME_SAMPLE` when readings are stale or still settling after each device state change.

For lights, extra wait times exist for large transitions:

```env
SLEEP_TIME_HUE=2
SLEEP_TIME_SAT=2
SLEEP_TIME_CT=1
SLEEP_TIME_EFFECT_CHANGE=5
```

## Resume behavior

The tool can resume many interrupted light sessions when `RESUME=true` and the partial CSV still exists. Docker users should keep the `export` and `.persistent` mounts in place between runs.
