# PowerCalc Visualization Tools

This directory contains tools for visualizing power consumption data for the PowerCalc project.

## Installation

The visualization tools require Python 3.13 and several dependencies. We recommend using [uv](https://github.com/astral-sh/uv) for dependency management.

### Installing with uv

1. Make sure you have uv installed. If not, you can install it following the instructions at [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv).

2. Install dependencies:

```bash
# Navigate to the utils/visualize directory
cd utils/visualize

# Install dependencies using uv sync
uv sync
```

This will automatically create a virtual environment and install all dependencies specified in the pyproject.toml file.

## Using plot.py

The `plot.py` script creates visualizations of power consumption data from CSV or JSON files.

### Basic Usage

```bash
uv run plot.py <file_path>
```

### Arguments

- `file_path`: Path to the CSV or JSON file containing power consumption data
- `--output`: (Optional) Path to save the plot image. Use "auto" to generate a filename based on the input file

### Examples

```bash
# Display a plot from a CSV file
uv run plot.py color_temp.csv

# Save the plot to an image file
uv run plot.py color_temp.csv --output plot.png

# Generate a plot from a JSON file with linear calibration data
uv run plot.py model.json
```

The script will automatically detect the file type and create an appropriate visualization.
