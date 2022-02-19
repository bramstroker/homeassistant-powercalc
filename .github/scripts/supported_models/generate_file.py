"""Update the manifest file."""
import glob
import json
import os
import sys

from pytablewriter import MarkdownTableWriter


def generate_supported_model_list():
    writer = MarkdownTableWriter()
    writer.header_list = [
        "manufacturer",
        "model id",
        "name",
        "calculation modes",
        "color modes",
    ]

    """Generate static file containing the supported models."""
    project_root = os.path.realpath(
        os.path.join(os.path.abspath(__file__), "../../../../")
    )
    with open(os.path.join(project_root, "docs/supported_models.md"), "w") as md_file:

        rows = []
        for json_path in glob.glob(
            f"{project_root}/custom_components/powercalc/data/*/*/model.json",
            recursive=True,
        ):
            with open(json_path) as json_file:
                model_directory = os.path.dirname(json_path)
                model_data = json.load(json_file)
                model = os.path.basename(model_directory)
                manufacturer = os.path.basename(os.path.dirname(model_directory))
                supported_modes = model_data["supported_modes"]
                name = model_data["name"]
                color_modes = get_color_modes(model_directory)
                rows.append(
                    [
                        manufacturer,
                        model,
                        name,
                        ",".join(supported_modes),
                        ",".join(color_modes),
                    ]
                )

        rows = sorted(rows, key=lambda x: (x[0], x[1]))
        writer.value_matrix = rows
        writer.table_name = f"Supported models ({len(rows)} total)"
        writer.dump(md_file)


def get_color_modes(model_directory) -> list:
    color_modes = set()
    for path in glob.glob(f"{model_directory}/**/*.csv.gz", recursive=True):
        filename = os.path.basename(path)
        index = filename.index(".")
        color_mode = filename[:index]
        color_modes.add(color_mode)
    return color_modes


generate_supported_model_list()
