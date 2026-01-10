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

## Find specific .csv.gz files recursively and loop over them
#for pattern in "color_temp.csv.gz" "brightness.csv.gz" "hs.csv.gz" "effects.csv.gz"; do
#  find "$SEARCH_DIR" -type f -name "$pattern" | while IFS= read -r file; do
#    echo "Processing $file"
#    relative_path=$(echo "$file" | sed "s|$SEARCH_DIR/||" | sed 's/.csv.gz$//')
#    output="$SEARCH_DIR/$relative_path.png"
#
#    process_file "$file" "$output"
#  done
#done

# Find all model.json files recursively and check if they have linear_config -> calibrate
find "$SEARCH_DIR" -type f -name "model.json" | while IFS= read -r file; do
  relative_path=$(echo "$file" | sed "s|$SEARCH_DIR/||")
  dir_depth=$(echo "$relative_path" | tr -cd '/' | wc -c)

  # Skip sub profiles (3 or more directories deep)
  if [ "$dir_depth" -eq 2 ] && grep -q "linear_config" "$file" && grep -q "calibrate" "$file"; then
    echo "Processing model.json file: $file"
    relative_path=$(echo "$relative_path" | sed 's/model.json$//')
    output="$SEARCH_DIR/${relative_path}calibration.png"

    process_file "$file" "$output"
  fi
done
