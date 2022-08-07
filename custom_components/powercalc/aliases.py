"""Aliases for manufacturers and model IDs."""

from __future__ import annotations


MANUFACTURER_SIGNIFY = "Signify Netherlands B.V."
MANUFACTURER_IKEA = "IKEA of Sweden"
MANUFACTURER_MULLER_LIGHT = "Müller Licht"
MANUFACTURER_YEELIGHT = "Yeelight"
MANUFACTURER_TUYA = "TuYa"
MANUFACTURER_AQARA = "Aqara"
MANUFACTURER_LEXMAN = "Lexman"
MANUFACTURER_MELITECH = "MeLiTec"
MANUFACTURER_WIZ = "WiZ"
MANUFACTURER_OSRAM = "OSRAM"
MANUFACTURER_LEDVANCE = "LEDVANCE"
MANUFACTURER_FEIBIT = "Feibit Inc co.  "

MANUFACTURER_ALIASES = {
    "Philips": MANUFACTURER_SIGNIFY,
    "IKEA": MANUFACTURER_IKEA,
    "Xiaomi": MANUFACTURER_AQARA,
    "LUMI": MANUFACTURER_AQARA,
    "ADEO": MANUFACTURER_LEXMAN,
    "MLI": MANUFACTURER_MULLER_LIGHT,
    "LightZone": MANUFACTURER_MELITECH,
}

MANUFACTURER_DIRECTORY_MAPPING = {
    MANUFACTURER_IKEA: "ikea",
    MANUFACTURER_FEIBIT: "jiawen",
    MANUFACTURER_LEDVANCE: "ledvance",
    MANUFACTURER_MULLER_LIGHT: "mueller-licht",
    MANUFACTURER_OSRAM: "osram",
    MANUFACTURER_SIGNIFY: "signify",
    MANUFACTURER_AQARA: "aqara",
    MANUFACTURER_LEXMAN: "lexman",
    MANUFACTURER_YEELIGHT: "yeelight",
    MANUFACTURER_TUYA: "tuya",
    MANUFACTURER_MELITECH: "melitec",
    MANUFACTURER_WIZ: "wiz",
}

MODEL_DIRECTORY_MAPPING = {
    "ikea": {
    },
    "ledvance": {"4058075168572": "Tibea TW Z3"},
    "mueller-licht": {
        "45327": "45318",
    },
    "osram": {
    },
    "signify": {
    },
    "yeelight": {
        "color2": "YLDP06YL",
        "ceiling10": "YLDL01YL",
        "mono1": "YLDP01YL",
        "strip6": "YLDD05YL",
        ### No profiles yet ###
        # "mono": "YLTD03YL",
        # "color6": "YLDP13AYL",
        # "colorb": "YLDP005",
        # "colorc": "YLDP004-A",
        # "RGBW": "MJDP02YL",
        # "lamp": "MJTD02YL",
        # "lamp1": "MJTD01YL",
        # "lamp15": "YLTD003",
        # "ceiling1": "YLXD01YL",
        # "ceiling2": "YLXD03YL",
        # "ceiling3": "YLXD05YL",
        # "ceiling4": "YLXD02YL",
        # "ceiling13": "YLXD01YL",
        # "ceil26": "YLXD76YL",
        # not a unique match, as it also may refer to "YLDP04YL"
        # "color4": "YLDP13YL",
        # not a unique match, as it also may refer to "YLDP03YL"
        # "color1": "YLDP02YL",
        # not a unique match, as it also may refer to "YLDD02YL"
        # "strip1": "YLDD01YL",
        # not a unique match, as it also may refer to "MJCTD02YL"
        # "bslamp1": "MJCTD01YL",
    },
}
