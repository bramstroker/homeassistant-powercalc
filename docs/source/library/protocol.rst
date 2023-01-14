## Light model library

The component ships with predefined light measurements for some light models.
This library will keep extending by the effort of community users.

These models are located in `config/custom_components/powercalc/data` directory.
You can also define your own models in `config/powercalc-custom-models` directory, when a manufacturer/model exists in this directory this will take precedence over the default data directory.

Each light model has it's own subdirectory `{manufacturer}/{modelid}`. i.e. signify/LCT010

### model.json

Every model MUST contain a `model.json` file which defines the supported calculation modes and other configuration.
See the [json schema](custom_components/powercalc/data/model_schema.json) how the file must be structured or the examples below.

When [LUT mode](#lut-mode) is supported also [CSV lookup files](#lut-data-files) must be provided.

Example lut mode:

```json
{
    "name": "Hue White and Color Ambiance A19 E26 (Gen 5)",
    "standby_power": 0.4,
    "calculation_strategy": "lut",
    "measure_method": "script",
    "measure_device": "Shelly Plug S"
}
```

Example linear mode

```json
{
    "name": "Hue Go",
    "calculation_strategy": "linear",
    "standby_power": 0.2,
    "linear_config": {
        "min_power": 0,
        "max_power": 6
    },
    "measure_method": "manual",
    "measure_device": "From manufacturer specifications"
}
```

### LUT data files

To calculate power consumption a lookup is done into CSV data files.

Depending on the supported color modes of the light the integration expects one or more CSV files here:
 - hs.csv.gz (hue/saturation, colored lamps)
 - color_temp.csv.gz (color temperature)
 - brightness.csv.gz (brightness only lights)

Some lights support two color modes (both hs and color_temp), so there must be two CSV files.

The files are gzipped to keep the repository footprint small, and installation fast but gzipping files is not mandatory.

Example:

```
- signify
  - LCT010
    - model.json
    - hs.csv.gz
    - color_temp.csv.gz
```

#### Expected file structure

- The file **MUST** contain a header row.
- Watt value decimal point must be a `.` not a `,`. i.e. `18.4`
- The data rows in the CSV files **MUST** have the following column order:

**hs.csv**
```csv
bri,hue,sat,watt
```

**color_temp.csv**
```csv
bri,mired,watt
```

**brightness.csv**
```csv
bri,watt
```

***Ranges***:
- brightness (0-255)
- hue (0-65535)
- saturation (0-255)
- mired (0-500)  min value depending on min mired value of the light model