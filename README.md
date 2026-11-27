# swagelok_scraper

Reichert SAP-B1-Artikel mit Produktdaten von Swagelok an (für den UNITE-Katalog).

Ablauf:

1. Artikel inkl. Preis aus SAP B1 (HANA) holen: `OITM` + Preisliste aus `ITM1`
   (nur gültige MTS-Artikel mit Preis > 0)
2. Pro `ItemCode` die Seite `https://products.swagelok.com/{lang}/p/{ItemCode}` lesen:
   Produktname, **eCl@ss** (4.1–10.1), **UNSPSC** (4.03–17.1001), Bild-URLs
3. Bilder nach `data_output/bilder/` herunterladen
4. Alles zusammen als Excel nach `data_output/swagelok_daten_<Zeitstempel>.xlsx` schreiben

## Einrichtung

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Zugangsdaten in `.env` im Projekt-Root (wird nicht versioniert):

```
HANA_HOST=...
HANA_PORT=30015
HANA_USER=...
HANA_PASSWORD=...
HANA_DATABASE_NAME=          # nur bei Multi-Tenant, sonst leer
HANA_SCHEMA=LEIPZ_PB1        # SAP-B1-Firmendatenbank
HANA_ENCRYPT=false
HANA_SSL_VALIDATE_CERTIFICATE=false
```

## Nutzung

```powershell
python src/main.py                 # 20 Artikel (Standard)
python src/main.py --limit 100
python src/main.py --limit 0       # alle Artikel
python src/main.py --no-bilder     # ohne Bild-Download
```

| Option | Bedeutung |
|---|---|
| `--limit N` | Anzahl Artikel aus OITM, `0` = alle (Standard: 20) |
| `--price-list N` | SAP-Preisliste (Standard: 1) |
| `--lang de` | Sprache der Produktseite (Standard: `en`) |
| `--pause 1.0` | Sekunden zwischen Anfragen an Swagelok |
| `--no-bilder` | keine Bilder herunterladen |
| `-o DATEI` | Ziel-Excel statt `data_output/swagelok_daten_<Zeitstempel>.xlsx` |

### Spalten im Ergebnis

| Spalte | Quelle |
|---|---|
| `ItemCode`, `ItemName`, `Price`, `Currency` | SAP |
| `Status` | `OK`, `nicht gefunden`, `HTTP …` oder `Fehler: …` |
| `Swagelok_Name` | Produktname laut Swagelok |
| `eClass …`, `UNSPSC …` | eine Spalte pro Version |
| `Bild`, `Bild_Zoom` | Bild-URLs bei Swagelok |
| `Bilddateien` | Dateinamen in `data_output/bilder/` |
| `URL` | Produktseite |

## Projektstruktur

```
src/
  main.py                      Einstiegspunkt (SAP -> Swagelok -> Excel)
  modules/
    db_functions.py            HANA-Verbindung, Artikelabfrage
    scraping_functions.py      Abruf und Auswertung der Swagelok-Seiten, Bild-Download
test/
  test_db_connection.py        interaktive Tests (# %%-Zellen) der DB-Funktionen
  scraper_swagelok.py          interaktive Tests der Scraping-Funktionen
data_output/                   Ergebnisse und Bilder (nicht versioniert)
```

## Hinweise

- Bildnamen bei Swagelok ≠ Artikelnummer (z. B. 177-13K-R4-A → `177-13K-R4-B.jpg`), daher wird
  die Bild-URL aus der Produktseite gelesen. Gespeichert wird als `<ItemCode>.<Endung>`.
- Bereits vorhandene Bilder werden übersprungen – abgebrochene Läufe können neu gestartet werden.
- Nicht alle Artikel haben bei Swagelok alle Klassifikationen hinterlegt; fehlende bleiben leer.
- Bei vielen Artikeln dauert ein Lauf entsprechend: ca. 2 Sekunden pro Artikel.
