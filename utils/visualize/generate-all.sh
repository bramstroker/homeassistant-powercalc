#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if a directory argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

# Directory to search (convert to absolute path)
SEARCH_DIR="$(realpath "$1")"

# Function to process a file with plot.py
process_file() {
  local file="$1"
  local output="$2"

  if [ -f "$output" ]; then
    echo "File $output already exists, skipping..."
    return
  fi

  # Call plot.py using the absolute path
  # Activate the virtual environment if it exists, otherwise run directly
  if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    python "$SCRIPT_DIR/plot.py" "$file" --output="$output"
    deactivate
  else
    python "$SCRIPT_DIR/plot.py" "$file" --output="$output"
  fi
}

# Find all .csv.gz files recursively and loop over them
find "$SEARCH_DIR" -type f -name "*.csv.gz" | while IFS= read -r file; do
  echo "Processing $file"
  relative_path=$(echo "$file" | sed "s|$SEARCH_DIR/||" | sed 's/.csv.gz$//')
  output="$SEARCH_DIR/$relative_path.png"

  process_file "$file" "$output"
done

# Find all model.json files recursively and check if they have linear_config -> calibrate
find "$SEARCH_DIR" -type f -name "model.json" | while IFS= read -r file; do
  # Check if the file contains both "linear_config" and "calibrate"
  if grep -q "linear_config" "$file" && grep -q "calibrate" "$file"; then
    echo "Processing model.json file: $file"
    relative_path=$(echo "$file" | sed "s|$SEARCH_DIR/||" | sed 's/model.json$//')
    output="$SEARCH_DIR/${relative_path}calibration.png"

    process_file "$file" "$output"
  fi
done
