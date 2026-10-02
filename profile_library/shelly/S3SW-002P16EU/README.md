# Shelly 2PM Gen3 – lokales Powercalc-Profil

Modell: **S3SW-002P16EU**. Ein Sensor erfasst den Eigenverbrauch des gesamten Geräts im Schalterbetrieb mit zwei Relais. Angeschlossene Verbraucher werden weiterhin von den Shelly-Messsensoren erfasst. Der Rollladenbetrieb ist mit diesem Profil nicht geprüft.

## Installation

1. ZIP direkt nach `/config/powercalc/profiles/` entpacken. Es muss anschließend `/config/powercalc/profiles/shelly/S3SW-002P16EU/model.json` geben. Die ZIP enthält bereits den Ordner `shelly/`; keinen weiteren Paketordner anlegen. Vorhandene eigene Dateien gleichen Namens vorher sichern.
2. Home Assistant neu starten, damit Powercalc die lokalen Profile einliest.
3. In Powercalc die Geräteerkennung bestätigen oder **Virtuelle Leistung (Bibliothek)** hinzufügen. Hersteller `shelly`, Modell `S3SW-002P16EU` / `2PM Gen3` wählen.
4. Passendes Subprofil auswählen und beide Ausgangs-Schalter des Shelly einbeziehen. Genau einen Eigenverbrauchssensor pro Gerät anlegen, damit der Grundverbrauch nicht doppelt gezählt wird.
5. Die berechnete Leistung bei beiden ausgeschalteten Relais mit „Grundverbrauch“ in der Tabelle vergleichen. Bei Änderung von BT, ECO oder AP das Subprofil in den Bibliotheksoptionen des Sensors anpassen.

WLAN bezeichnet den verbundenen WLAN-Client, BT Bluetooth, AP den Access Point und ECO den Eco-Modus. Die Profilnamen entsprechen den Messläufen im Chat. Weitere Betriebsbedingungen wie Repeater, Signalstärke und Firmware wurden nicht festgehalten. Es erfolgt keine automatische Erkennung oder Änderung dieser Einstellungen.

## Werte

`Leistung = Grundverbrauch + Anzahl eingeschalteter Relais × Relaiswert`.
Das Hauptprofil enthält WLAN als Basis; alle acht Subprofile überschreiben die beiden Leistungswerte ausdrücklich.

| Subprofil | Grundverbrauch W | je Relais W | beide an W | maximale Modellabweichung W |
|---|---:|---:|---:|---:|
| `wlan` | 0.62 | 0.33 | 1.28 | 0.035 |
| `wlan_bt` | 0.655 | 0.3025 | 1.2600 | 0.0325 |
| `wlan_eco` | 0.595 | 0.2075 | 1.0100 | 0.0225 |
| `wlan_bt_eco` | 0.44 | 0.2925 | 1.0250 | 0.0125 |
| `wlan_ap` | 0.675 | 0.2925 | 1.2600 | 0.0775 |
| `wlan_ap_bt` | 0.7 | 0.315 | 1.330 | 0.045 |
| `wlan_ap_eco` | 0.64 | 0.31 | 1.26 | 0.11 |
| `wlan_ap_bt_eco` | 0.655 | 0.3025 | 1.2600 | 0.0225 |

Die vier Nachkommastellen einiger Relaiswerte bewahren das Rechenergebnis; sie sind keine Aussage über die Messgenauigkeit. WLAN+ECO: 9,695 − 9,1 = **0,595 W**; (10,11 − 9,695) / 2 = **0,2075 W** je Relais.

Messmethode und sämtliche Messläufe: [MEASUREMENTS.md](MEASUREMENTS.md), [measurements.csv](measurements.csv). Englischer PR-Text: [PR_SUMMARY.md](PR_SUMMARY.md).

## Format und Prüfung

Herstellerdatei und Hauptprofil sowie die acht mit dem Hauptprofil zusammengeführten Subprofile wurden gegen die aktuellen Powercalc-JSON-Schemata geprüft. Rechenwerte, Zustände und ZIP-Struktur wurden lokal geprüft. Ein Laufzeittest in deiner Home-Assistant-Installation steht noch aus.

Grundlagen: [lokale Profile](https://docs.powercalc.nl/library/library/), [Subprofile](https://docs.powercalc.nl/library/sub-profiles/), [Smart-Switch-Eigenverbrauch](https://docs.powercalc.nl/library/device-types/smart-switch/).
