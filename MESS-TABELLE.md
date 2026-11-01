# Plug S Gen3 (S3PL-00112EU) – Subprofile neu messen

Messaufbau wie beim Plug M Gen3: **Dummy-Last, Mittelwert über 300 s**, Referenzmessgerät Shelly Plug S Gen3.
Pro Zeile zwei Werte eintragen: **Relais AUS** → `standby_power` · **Relais AN** → `standby_power_on`.

| # | Ordner | Anzeigename | standby_power (AUS) | standby_power_on (AN) |
|---|--------|-------------|---------------------|------------------------|
| 1 | `+wlan` | +WLAN | | |
| 2 | `+wlan_+led` | +WLAN +LED | | |
| 3 | `+wlan_+bt` | +WLAN +BT | | |
| 4 | `+wlan_+bt_+led` | +WLAN +BT +LED | | |
| 5 | `+wlan_+eco` | +WLAN +ECO | | |
| 6 | `+wlan_+eco_+led` | +WLAN +ECO +LED | | |
| 7 | `+wlan_+eco_+bt` | +WLAN +ECO +BT | | |
| 8 | `+wlan_+eco_+bt_+led` | +WLAN +ECO +BT +LED | | |
| 9 | `+wlan_+ap` | +WLAN +Wifi-AP | | |
| 10 | `+wlan_+ap_+led` | +WLAN +Wifi-AP +LED | | |
| 11 | `+wlan_+ap_+bt` | +WLAN +Wifi-AP +BT | | |
| 12 | `+wlan_+ap_+bt_+led` | +WLAN +Wifi-AP +BT +LED | | |
| 13 | `+wlan_+eco_+ap` | +WLAN +ECO +Wifi-AP | | |
| 14 | `+wlan_+eco_+ap_+led` | +WLAN +ECO +Wifi-AP +LED | | |
| 15 | `+wlan_+eco_+ap_+bt` | +WLAN +ECO +Wifi-AP +BT | | |
| 16 | `+wlan_+eco_+ap_+bt_+led` | +WLAN +ECO +Wifi-AP +BT +LED | | |

## Nicht vergessen

- **BT-Pairing**: BT muss wirklich aktiv *verbunden* sein, nicht nur eingeschaltet – sonst misst du den falschen Zustand.
- **Wifi-AP**: Repeater/Range Extender einschalten. Der AP-Zustand zieht deutlich mehr als WLAN-Client.
- **LED**: Helligkeit und Modus notieren (z. B. „100% grün/rot, Schaltzustandsanzeige") – beim Plug S bekannt fehlerhaft im ECO-Modus.
- **WLAN-RSSI** notieren (z. B. -40 dBm), steht in `measure_description`.
- **Firmware-Version** des Geräts notieren.

## Nach dem Messen

1. Werte in die `model.json` der jeweiligen Ordner eintragen.
2. In der Haupt-`model.json` aktualisieren: `measure_description`, `measure_settings`, ggf. `measure_device`.
3. Committen und pushen auf `Add-more-Sub-Profiles-S3PL-00112EU`.
