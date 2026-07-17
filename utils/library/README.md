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

### `validate_model_json.py`

Validate every `profile_library/**/model.json` against `profile_library/model_schema.json`.
Prints `VALID` / `INVALID` / `ERROR` per file.

```bash
uv run --group library python -m utils.library.validate_model_json
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
