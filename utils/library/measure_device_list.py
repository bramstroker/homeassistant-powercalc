import json
import os
from collections import Counter
from collections.abc import Generator


def find_model_json_files(directory: str) -> Generator:
    """Recursively find all model.json files in a directory."""
    for root, _, files in os.walk(directory):
        for file in files:
            if file == "model.json":
                yield os.path.join(root, file)


def extract_measure_device(file_path: str) -> str | None:
    """Extract the measure_device property from a model.json file."""
    try:
        with open(file_path) as f:
            data = json.load(f)
            return data.get("measure_device")
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading {file_path}: {e}")  # noqa: T201
        return None


def count_measure_devices(directory: str) -> Counter:
    """Count occurrences of each measure_device in all model.json files."""
    measure_device_counter = Counter()

    for file_path in find_model_json_files(directory):
        measure_device = extract_measure_device(file_path)
        if measure_device:
            measure_device_counter[measure_device] += 1

    return measure_device_counter


def main() -> None:
    directory = os.path.join(os.path.dirname(__file__), "../../profile_library")

    counts = count_measure_devices(directory)

    # Display sorted results
    print("\nMeasure Device Counts:")  # noqa: T201
    for device, count in counts.most_common():
        print(f"{device}: {count}")  # noqa: T201


if __name__ == "__main__":
    main()
