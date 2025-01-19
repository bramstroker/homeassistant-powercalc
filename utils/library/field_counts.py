from collections import Counter

from utils.library.common import find_model_json_files


def count_field(field_name: str) -> Counter:
    """Count occurrences of each measure_device in all model.json files."""
    counter = Counter()

    for model_data in find_model_json_files():
        value = model_data["data"].get(field_name)
        if value:
            counter[value] += 1

    return counter


def main() -> None:
    counts = count_field("measure_device")

    # Display sorted results
    print("\nCounts:")  # noqa: T201
    for val, count in counts.most_common():
        print(f"{val}: {count}")  # noqa: T201


if __name__ == "__main__":
    main()
