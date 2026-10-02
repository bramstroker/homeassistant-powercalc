# Messprotokoll – Shelly 2PM Gen3

- Gerät: Shelly 2PM Gen3, S3SW-002P16EU; Gerätekennung `shelly2pmg3-d0cf13d91544`.
- Messgerät: Shelly Plug S `1D3A67`; externe Leistungsmessung des Eigenverbrauchs.
- Datum: 02.10.2026. Uhrzeiten aus dem Chat, Europe/Berlin (UTC+02:00).
- Vier Relaiszustände je Konfiguration: 00 = beide aus, 10 = Output 0 an, 01 = Output 1 an, 11 = beide an.
- Je Zustand 60-s-Mittelwert; Messausgabe aus dem im Chat verwendeten Skript. Einzelsamples und Skriptquelltext liegen diesem Paket nicht bei.
- WLAN+ECO um 11:07:13: zusätzliche konstante Dummy-Last parallel zum 2PM hinter dem Messgerät. Separate Dummy-Messung ohne 2PM: ungefähr 9,1 W. Der Nutzer hat in diesem Folgechat bestätigt, dass auch dieser Wert ein 60-s-Mittelwert ist. Der Wert ist nur mit einer Nachkommastelle überliefert.

## Vollständige überlieferte Messreihen

Die folgenden Werte sind die gemeldeten Mittelwerte vor Dummy-Abzug. `selected` bezeichnet den übernommenen Lauf, `superseded` die durch eine Wiederholung ersetzte Messung und `rejected_zero_baseline` die nicht verwendeten 0-W-Grundmessungen.

| Profil | Uhrzeit | 00 W | 10 W | 01 W | 11 W | Dummy W | Verwendung |
|---|---|---:|---:|---:|---:|---:|---|
| WLAN | 09:36:51 | 0.62 | 0.915 | 0.94 | 1.28 | 0 | selected |
| WLAN + BT | 09:42:30 | 0.655 | 0.96 | 0.925 | 1.26 | 0 | selected |
| WLAN + ECO | 09:48:56 | 0 | 0.5 | 0.54 | 0.84 | 0 | rejected_zero_baseline |
| WLAN + BT + ECO | 09:54:11 | 0.44 | 0.72 | 0.725 | 1.025 | 0 | selected |
| WLAN + AP | 10:00:00 | 0.675 | 1.045 | 0.955 | 1.26 | 0 | selected |
| WLAN + AP + BT | 10:05:48 | 0.7 | 0.97 | 0.995 | 1.33 | 0 | selected |
| WLAN + AP + ECO | 10:11:29 | 0.615 | 1 | 1 | 1.205 | 0 | superseded |
| WLAN + AP + BT + ECO | 10:16:39 | 0.655 | 0.98 | 0.975 | 1.26 | 0 | selected |
| WLAN + ECO | 10:45:56 | 0 | 0.5 | 0.58 | 0.83 | 0 | rejected_zero_baseline |
| WLAN + AP + ECO | 10:52:10 | 0.64 | 0.96 | 1.06 | 1.26 | 0 | selected |
| WLAN + ECO | 11:07:13 | 9.695 | 9.89 | 9.88 | 10.11 | 9.1 | selected |

## Ableitung

Für jeden gewählten Lauf gilt:

```text
Pxy = gemessene Gesamtleistung im Zustand xy − separat gemessene Dummy-Last
standby_power = P00
multi_switch_config.power = (P11 − P00) / 2
P_Modell(x,y) = standby_power + (x+y) × multi_switch_config.power
```

Für Messungen ohne Dummy wird keine zusätzliche Last abgezogen. WLAN+ECO korrigiert: 00 = 0,595 W, 10 = 0,790 W, 01 = 0,780 W, 11 = 1,010 W. Der Relaiswert ist 0,2075 W. Er ist unabhängig vom konstanten Dummy-Offset; der Grundverbrauch hängt direkt von dessen Genauigkeit und Stabilität ab.

Der gemeinsame Relaiswert entspricht auch dem Mittel der vier im Chat berichteten Relaisdifferenzen. Die Chat-Ausgaben enthalten gerundete Kandidaten (z. B. 0,302 statt rechnerisch 0,3025 W). Das Paket berechnet die Werte nachvollziehbar aus den überlieferten Zustandsmitteln neu und behält vier Nachkommastellen bei, wo erforderlich. Es handelt sich nicht um neue Messungen.

Die beiden WLAN+ECO-Läufe mit 0 W im Zustand 00 werden nicht als echte Grundverbrauchsmessung verwendet. Ihre Ursache ist aus den Daten allein nicht bewiesen. Für WLAN+AP+ECO wird der letzte Lauf um 10:52:10 verwendet; die ältere Messung bleibt im Protokoll erhalten.

## Modellgrenzen

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

Ein gemeinsamer Relaiswert bildet unterschiedliche Einzelrelaiswerte und Messstreuung nur näherungsweise ab. Bei WLAN+AP+ECO berechnet das Modell für beide Einzelzustände 0,95 W; gemessen wurden 0,96 bzw. 1,06 W. Die größte Abweichung beträgt daher 0,11 W. Es werden keine statistische Unsicherheit und keine zusätzliche Genauigkeit aus der Zahl der Dezimalstellen abgeleitet.

Firmware, Versorgungsspannung, Abtastrate, Einschwingzeit, Signalstärke, Repeaterstatus, genaue Verdrahtung und Kalibrierung sind nicht dokumentiert. Die acht Konfigurationen werden als empirische Einzelmessreihen bereitgestellt; daraus werden keine allgemeingültigen Mehrverbräuche einzelner Funkfunktionen abgeleitet.

Quelle: vom Nutzer gepostete Messausgaben im Chat „Powercalc Shelly Sensor integrieren“ und Bestätigung der Dummy-Mittelung im Folgechat. Rohdaten im engeren Sinn (zeitgestempelte Einzelsamples) sind nicht verfügbar; die CSV enthält Zustandsmittelwerte.
