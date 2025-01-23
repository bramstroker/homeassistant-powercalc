from collections.abc import Callable, Mapping

import pytablewriter

from utils.library.common import find_model_json_files


def build_list(filter_callback: Callable | None, fields: list[str]) -> list[Mapping[str, str]]:
    """Count occurrences of each measure_device in all model.json files."""
    listing = []
    for model_data in find_model_json_files():
        json_data = model_data["data"]
        if filter_callback and not filter_callback(json_data):
            continue
        entry_data = {
            "manufacturer": model_data["manufacturer"],
            "model": model_data["model"],
            "sub_profile": model_data["sub_profile"],
        }
        entry_data.update({field: json_data.get(field) for field in fields})
        listing.append(entry_data)
    return listing


def write_md_table(data: list[Mapping[str, str]], output_file: str) -> None:
    """Write the listing data to a Markdown table using pytablewriter."""
    writer = pytablewriter.MarkdownTableWriter()
    writer.table_name = "Device Power Data"
    fields = data[0].keys()
    writer.headers = fields
    writer.value_matrix = [[row.get(field, "") for field in fields] for row in data]

    with open(output_file, "w") as f:
        writer.stream = f
        writer.write_table()


def main() -> None:
    fields = ["standby_power", "standby_power_on", "fixed_config", "only_self_usage"]
    listing = build_list(
        lambda j: j.get("device_type") == "smart_switch",
        fields,
    )

    # Write the result to a Markdown file
    output_file = "device_power_data.md"
    write_md_table(listing, output_file)


if __name__ == "__main__":
    main()
