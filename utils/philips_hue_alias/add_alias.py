import os
import sys
import json
from typing import List

signify_path = "profile_library/signify"
csv_path = "utils/philips_hue_alias/hue-effect-compatible-hue-lights.csv"
# CSV data source: https://www.assets.signify.com/is/content/Signify/Assets/hue/global/20221019-effects-compatible-lights.pdf

def parse_csv() -> dict:
    art_to_code = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        for line in f.readlines()[1:]:
            code, _, art = line.strip().split(',')
            if not art in art_to_code:
                art_to_code[art] = []
            art_to_code[art].append(code)

    return art_to_code

def add_alias(signify_devices: List[str], art_to_code: dict) -> None:
    for device in signify_devices:
        if not device in art_to_code:
            print(f"device {device} not found in csv. Skipping it")
            continue

        json_file = os.path.join(signify_path, device, 'model.json')

        with open(json_file, "r") as jsonFile:
            data = json.load(jsonFile)

        if "aliases" not in data:
            data["aliases"] = []

        data["aliases"] += art_to_code[device]
        data["aliases"] = sorted(list(set(data["aliases"])))

        with open(json_file, "w") as jsonFile:
            json.dump(data, jsonFile, indent=2, sort_keys=True)
            jsonFile.write('\n')

def main() -> None:
    if not os.path.exists(signify_path):
        print("signify path not found. Did you run the script from the repo root dir?")
        sys.exit(0)

    signify_devices = [f.name for f in os.scandir(signify_path) if f.is_dir()]
    art_to_code = parse_csv()
    print(art_to_code)
    add_alias(signify_devices, art_to_code)

if __name__ == "__main__":
    main()
