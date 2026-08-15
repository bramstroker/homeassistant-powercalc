# Profile library utilities

Helper scripts for inspecting and validating the profiles under `profile_library/`.

## Setup

These scripts use absolute imports (`utils.library.*`) and must be run **from the
repository root** as modules. Their dependencies live in the `library`
[dependency group](../../pyproject.toml) and are installed automatically by
`uv run --group library`:

```bash
# from the repository root
cd /path/to/powercalc
```

## Scripts

### `update_library.py`

Generate the profile-library index, populate missing author metadata, and add custom
profile fields to the English translation file. This is normally run by the update
workflow after a profile change. The index records the LUT quality scores from
[`scan_lut_quality.py`](#scan_lut_qualitypy) per profile, which the
[library website](https://library.powercalc.nl) renders and filters on.

```bash
uv run --group profile-library python -m utils.library.update_library --library-json
```

### `validate_model_json.py`

Validate every `profile_library/*/manufacturer.json` against
`profile_library/manufacturer_schema.json` and every `profile_library/*/*/model.json`
against `profile_library/model_schema.json`. Prints `VALID` / `INVALID` / `ERROR` per
file.

```bash
uv run --group library python -m utils.library.validate_model_json
```

### `validate_lut_files.py`

Validate the structure of every LUT (`*.csv.gz`) file in the library: the columns and
value ranges required for its color mode, whether the measurements reach the top of the
brightness range, and whether each profile exposes a color mode combination Home
Assistant can report. Accepts an optional directory; defaults to the whole library.
Exits non-zero when a problem is found, and runs on every pull request touching a LUT.

```bash
uv run --group library python -m utils.library.validate_lut_files

# validate a single manufacturer
uv run --group library python -m utils.library.validate_lut_files profile_library/signify
```

### `scan_lut_quality.py`

Scan LUT (`*.csv.gz`) files for rough curves and outliers. Accepts an optional
path (a profile directory or a single CSV file); defaults to the whole library.

```bash
# scan the whole library
uv run --group library python -m utils.library.scan_lut_quality

# scan a single profile or CSV, only color_temp LUTs, JSON output
uv run --group library python -m utils.library.scan_lut_quality \
    profile_library/signify/929003736201 --mode color_temp --format json
```

Useful options (see `--help` for the full list):

- `--mode {all,brightness,color_temp,...}` — restrict to one color mode.
- `--format {text,json}` — output format.
- `--severity` / `--min-score` / `--show-ok` — filter what is reported.
- `--fail-under <score>` / `--fail-on-issues` — exit non-zero (for CI).
- `--fix <mode>` — automatically remove or correct offending points.

### `build_info_table.py`

Generate a Markdown table of smart-switch power data, written to
`device_power_data.md` in the current directory.

```bash
uv run --group library python -m utils.library.build_info_table
```

### `csv_row_counts.py`

List the number of data points (rows, excluding the header) per CSV file in the
library, including gzipped CSVs, followed by a total. Accepts an optional
directory; defaults to the whole library.

```bash
uv run --group library python -m utils.library.csv_row_counts

# largest files first
uv run --group library python -m utils.library.csv_row_counts --sort rows
```

### `field_counts.py`

Print the value counts for a profile field (defaults to `measure_device`).

```bash
uv run --group library python -m utils.library.field_counts [field]
```

## Tests

The tests are included in the root `pytest` configuration:

```bash
uv run --group library pytest utils/library/tests
```
