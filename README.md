# swagelok_scraper

Scraping von Produktdaten für den UNITE-Katalog: liest pro Swagelok-Artikelnummer
die Produktseite `https://products.swagelok.com/{lang}/p/{Artikelnummer}` und
extrahiert Produktname, **eCl@ss** (4.1–10.1), **UNSPSC** (4.03–17.1001) und Produktbilder.

Nur Python-Standardbibliothek (getestet mit Python 3.14), keine Installation nötig.

## Nutzung

1. Artikelnummern als `.txt` oder `.csv` (erste Spalte, Kopfzeile optional) nach `data_input/` legen.
2. Starten:

```powershell
python src/scraper_swagelok.py            # alle Dateien aus data_input/
python src/scraper_swagelok.py --bilder   # zusätzlich Bilder nach data_output/bilder/
```

Ergebnis: `data_output/swagelok_daten_<Zeitstempel>.csv` (Semikolon, UTF-8 mit BOM → öffnet direkt in Excel).

### Optionen

| Option | Bedeutung |
|---|---|
| `ART1 ART2 …` | Artikelnummern direkt angeben (statt data_input/) |
| `-i DATEI` | bestimmte Eingabedatei(en), mehrfach möglich |
| `-o DATEI` | Ziel-CSV |
| `--bilder [ORDNER]` | Bilder herunterladen (Standard: `data_output/bilder`) |
| `--lang de` | Sprache der Produktseite (Standard `en`) |
| `--pause 1.0` | Sekunden zwischen Anfragen |

## Hinweise

- Bildnamen bei Swagelok ≠ Artikelnummer (z. B. 177-13K-R4-A → `177-13K-R4-B.jpg`), daher wird
  die Bild-URL aus der Produktseite gelesen. Gespeichert wird als `<Artikelnummer>.jpg`.
- Bereits vorhandene Bilder werden übersprungen – abgebrochene Läufe können neu gestartet werden.
- Unbekannte Artikelnummern erscheinen mit Status `nicht gefunden` in der CSV.
- Inhalte von `data_input/` und `data_output/` werden nicht versioniert (außer `beispiel.txt`).
