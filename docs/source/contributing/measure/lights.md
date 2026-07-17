# Light profiles

Light profiles usually use the `lut` strategy. The measure tool creates one CSV file for each measured light mode and can generate a matching `model.json`.

## Before measuring

Check the light entity in Home Assistant:

1. Open `Developer tools` -> `States`.
2. Search for the light entity.
3. Note the `supported_color_modes` attribute.
4. Pause automations that can change the light during the measurement.

Run the measure tool once for every relevant supported color mode.

| Home Assistant capability | Measure tool mode |
| --- | --- |
| `brightness` | `brightness` |
| `color_temp` | `color_temp` |
| `hs` | `hs` |
| `xy` | `hs` |
| `white` | `white` |
| `effect` | `effect` |

`xy` and `hs` are different representations of color. Use `hs` in the measure tool when the light reports `xy`.

## Configure the controller

Use the Home Assistant controller for most lights:

```env
LIGHT_CONTROLLER=hass
HASS_URL=http://homeassistant.local:8123/api
HASS_TOKEN=your_long_lived_access_token
```

You can also control Hue lights through a Hue bridge:

```env
LIGHT_CONTROLLER=hue
HUE_BRIDGE_IP=x.x.x.x
```

Native installations need the optional direct-Hue dependency. Install it and keep the extra enabled when starting the wizard:

```bash
uv sync --extra dev --extra cli
uv run --extra cli python -m measure.measure
```

The script asks you to select a Home Assistant light entity or enter a Hue light/group identifier, depending on the selected controller.

## Run the light measurement

Start the tool and select `Light bulb(s)` when asked for the measurement type. The wizard asks for:

- Whether to generate `model.json`.
- Whether to use a dummy load.
- Model ID and full model name.
- The power meter model used for the measurement.
- The light entity and one or more LUT modes.
- Whether to gzip the CSV output.

The script changes the light to each brightness, color, color temperature, or effect variation and records the measured wattage.

The run can take from minutes to several hours. Color and effect measurements are much longer than brightness-only measurements.

## Brightness and color precision

The defaults keep profile generation practical. Increase precision only when you deliberately want a denser LUT and accept a longer measurement run.

```env
MIN_BRIGHTNESS=1
HS_BRI_PRECISION=1.0
HS_HUE_PRECISION=1.0
HS_SAT_PRECISION=1.0
CT_BRI_STEPS=5
CT_MIRED_STEPS=10
```

Notes:

- Increase `MIN_BRIGHTNESS` when the light turns off or behaves unreliably at brightness `1`.
- Higher HS precision means more measurements.
- Manual power meter mode uses coarser steps to keep the session manageable.

## Multiple identical lights

When standby power is too low for your meter, measuring multiple identical lights in parallel can make the total load measurable. The wizard asks whether you are measuring multiple lights and how many lights are connected.

Only use this when every connected light is the same model and receives the same commands. See [Standby troubleshooting](standby_troubleshooting.md) for details.

## Effect measurements

Effect measurements are different because effects can fluctuate over time. The tool measures each effect and brightness combination for up to `MEASURE_TIME_EFFECT` seconds and can stop earlier when the cumulative average has stabilized.

```env
MEASURE_TIME_EFFECT=180
MEASURE_TIME_EFFECT_MIN=20
MEASURE_TIME_EFFECT_CONVERGENCE_WINDOW=15
MEASURE_TIME_EFFECT_CONVERGENCE_ABS=0.10
MEASURE_TIME_EFFECT_CONVERGENCE_REL=1.0
EFFECT_BRI_STEPS=10
```

Use a longer `MEASURE_TIME_EFFECT` for random effects such as sparkle, fire, candle, or other dynamic animations. Stable effects usually finish earlier when the average converges.

## Dummy load

A dummy load is a stable resistive load connected in parallel with the measured light. It can help power meters that are inaccurate at very low loads.

Use a dummy load only when you understand the wiring and safety implications. The power meter must support voltage readings so the tool can subtract the dummy load contribution correctly.

Do not use an LED bulb as a dummy load. Use a stable resistive load, such as a small incandescent bulb, when this method is needed. See [Standby troubleshooting](standby_troubleshooting.md) for more detail about using a dummy load for low standby readings.

In the Home Assistant app, enable the resistive dummy load during measurement setup. The app calibrates a warmed-up load for at least 20 periods of 30 seconds and continues when its resistance is not yet stable. A stored calibration can be reused only after confirming that the same warmed-up load is connected; choose **Recalibrate** after changing the load, meter, or wiring. Keep the load connected throughout the measurement. The app subtracts its calculated consumption from live and saved power readings.

## Inspecting light output

A successful light run creates files such as:

```text
export/<model_id>/model.json
export/<model_id>/brightness.csv.gz
export/<model_id>/color_temp.csv.gz
export/<model_id>/hs.csv.gz
export/<model_id>/effect.csv.gz
```

Before submitting, inspect the CSV data for obvious issues:

- Repeated `0` W values while the light was on.
- Large jumps that do not match brightness or color changes.
- Missing color modes that the light supports.
- Wrong model ID or model name in `model.json`.

If the uncompressed `.csv` and `.csv.gz` both exist, keep the `.csv.gz` file for submission.
