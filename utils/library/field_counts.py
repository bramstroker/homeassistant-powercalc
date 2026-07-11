import argparse
from collections import Counter

from utils.library.common import find_model_json_files


def count_field(field_name: str) -> Counter:
    """Count occurrences of each value for the given field in all model.json files."""
    counter = Counter()

    for model_data in find_model_json_files():
        value = model_data["data"].get(field_name)
        if value:
            counter[value] += 1

    return counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Count value occurrences for a profile field in all model.json files.")
    parser.add_argument(
        "field",
        nargs="?",
        default="measure_device",
        help="The profile field to count (default: measure_device)",
    )
    args = parser.parse_args()

    counts = count_field(args.field)

    # Display sorted results
    print("\nCounts:")  # noqa: T201
    for val, count in counts.most_common():
        print(f"{val}: {count}")  # noqa: T201


if __name__ == "__main__":
    main()
