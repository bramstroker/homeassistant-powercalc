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

# Find all .csv.gz files recursively and loop over them
find "$SEARCH_DIR" -type f -name "*.csv.gz" | while IFS= read -r file; do
  echo "Processing $file"
  relative_path=$(echo "$file" | sed "s|$SEARCH_DIR/||" | sed 's/.csv.gz$//')
  output="$SEARCH_DIR/$relative_path.png"

  if [ -f "$output" ]; then
    echo "File $relative_path already exists, skipping..."
    continue
  fi

  # Call plot.py using the absolute path
  poetry run python "$SCRIPT_DIR/plot.py" "$file" --output="$output"
done
