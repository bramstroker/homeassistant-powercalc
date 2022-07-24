"""Aliases for manufacturers and model IDs."""

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
    MANUFACTURER_IKEA: {
        "FLOALT panel WS 30x30": "L1527",
        "FLOALT panel WS 60x60": "L1529",
        "Slagsida": "L1616",
        "TRADFRI bulb E14 WS opal 400lm": "LED1536G5",
        "TRADFRI bulb GU10 WS 400lm": "LED1537R6",
        "TRADFRI bulb E27 WS opal 980lm": "LED1545G12",
        "TRADFRI bulb E27 WS clear 950lm": "LED1546G12",
        "TRADFRI bulb E27 opal 1000lm": "LED1623G12",
        "TRADFRI bulb E27 W opal 1000lm": "LED1623G12",
        "TRADFRI bulb E14 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E26 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E27 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E14 W op/ch 400lm": "LED1649C5",
        "TRADFRI bulb GU10 W 400lm": "LED1650R5",
        "TRADFRI bulb E27 WS opal 1000lm": "LED1732G11",
        "TRADFRI bulb E14 WS opal 600lm": "LED1733G7",
        "TRADFRI bulb E27 WS clear 806lm": "LED1736G9",
        "TRADFRI bulb E14 WS 470lm": "LED1835C6",
        "TRADFRI bulb E27 WW 806lm": "LED1836G9",
        "TRADFRI bulb E27 WW clear 250lm": "LED1842G3",
        "TRADFRI bulb GU10 WW 400lm": "LED1837R5",
        "TRADFRI bulb GU10 CWS 345lm": "LED1923R5",
        "TRADFRI bulb E27 CWS 806lm": "LED1924G9",
        "TRADFRI bulb E14 CWS 470lm": "LED1925G6",
        "TRADFRIbulbE14WScandleopal470lm": "LED1949C5",
        "TRADFRIbulbE14WSglobeopal470lm": "LED2002G5",
        "TRADFRIbulbE14WWclear250lm": "LED1935C3",
        "TRADFRIbulbE27WSglobeopal1055lm": "LED2003G10",
        "TRADFRIbulbE27WWclear250lm": "LED1934G3",
        "TRADFRIbulbGU10WS345lm": "LED2005R5",
        "TRADFRI bulb GU10 WW 345lm": "LED2005R5",
        "LEPTITER Recessed spot light": "T1820",
    },
    MANUFACTURER_LEDVANCE: {"4058075168572": "Tibea TW Z3"},
    MANUFACTURER_MULLER_LIGHT: {
        "45327": "45318",
    },
    MANUFACTURER_OSRAM: {"AC03642": "CLA60 TW"},
    MANUFACTURER_SIGNIFY: {
        "9290022166": "LCA001",
        "929003053401": "LCA001",
        "9290024687": "LCA007",
        "929002471601": "LCA008",
        "929001953101": "LCG002",
        "1741430P7": "LCS001",
        "1741530P7": "LCS001",
        "9290012573A": "LCT015",
        "440400982841": "LCT024",
        "7602031P7": "LCT026",
        "9290022169": "LTA001",
        "9290024719": "LTA011",
        "3261030P6": "LTC001",
        "3261031P6": "LTC001",
        "3261048P6": "LTC001",
        "3418931P6": "LTC012",
        "3417711P6": "LTW017",
        "8718699673147": "LWA001",
        "9290022268": "LWA003",
        "9290023351": "LWA008",
        "433714": "LWB004",
        "8718696449691": "LWB010",
        "9290022415": "LWO002",
        "9290024406": "LWU001",
        "9290011370B": "LWF001",
        "046677551780": "LWV002",
        "8719514328242": "LTA004",
        "8718699703424": "LCL001",
        "8718699671211": "LWE002",
        "9290020399": "LWE002",
        "915005106701": "LST002",
        "7299355PH": "LST001",
        "9290024684": "LTA009",
        # US Versions. Alias to EU versions
        "LCA005": "LCA001",
        "9290022266A": "LCA001",
    },
    MANUFACTURER_TUYA: {
        "TS0505B": "NO66-ZB/length_5",
    },
    MANUFACTURER_YEELIGHT: {
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
