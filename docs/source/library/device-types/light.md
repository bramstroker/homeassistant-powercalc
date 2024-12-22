# Light

Lights are integrated by using the [LUT](../../strategies/lut.md) (Look Up Table) strategy.
This strategy is used to calculate the power consumption of the light based on the brightness / color levels.
To generate a LUT you'll need to use the [measure utility](../../contributing/measure.md).
This will fully automate the process and generate the required CSV files and model.json.

Example model.json:

```json
{
    "name": "Hue White and Color Ambiance A19 E26 (Gen 5)",
    "standby_power": 0.4,
    "calculation_strategy": "lut",
    "measure_method": "script",
    "measure_device": "Shelly Plug S"
}
```

## LUT data files

Depending on the supported color modes of the light the integration expects one or more CSV files.
You can check the supported modes in HA Developer Tools.

> - hs.csv.gz (hue/saturation, colored lamps)
> - color_temp.csv.gz (color temperature)
> - brightness.csv.gz (brightness only lights)

Some lights support two color modes (both `hs` and `color_temp`), so there must be two CSV files.
When your light supports `xy` color mode, you just need to provide the `hs` CSV file.

The files must be gzipped to keep the repository footprint small.

Example directory structure:

```
- signify
  - LCT010
    - model.json
    - hs.csv.gz
    - color_temp.csv.gz
```

### Expected file structure

- The file **MUST** contain a header row.
- Watt value decimal point must be a `.` not a `,`. i.e. `18.4`
- The data rows in the CSV files **MUST** have the following column order:

**hs.csv**

```text
bri,hue,sat,watt
```

**color_temp.csv**

```text
bri,mired,watt
```

**brightness.csv**

```text
bri,watt
```

**\*Ranges\***:

- brightness (0-255)
- hue (0-65535)
- saturation (0-255)
- mired (0-500)  min value depending on min mired value of the light model