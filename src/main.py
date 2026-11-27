"""Swagelok-Produktdaten-Scraper (Einstiegspunkt).

Ablauf:
    1. Artikel inkl. Preis aus SAP B1 (OITM/ITM1) holen
    2. Für jeden ItemCode die Swagelok-Produktseite scrapen
       (Name, eCl@ss, UNSPSC, Bild-URLs) und Bilder nach data_output/bilder laden
    3. Swagelok-Daten an die SAP-Daten anhängen
    4. Ergebnis als Excel nach data_output/ schreiben

Beispiele:
    python src/main.py                  # 20 Artikel (Standard)
    python src/main.py --limit 100
    python src/main.py --limit 0        # alle Artikel
    python src/main.py --no-bilder      # ohne Bild-Download
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from modules.db_functions import get_connection, get_top_items
from modules.scraping_functions import log, scrape_items

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data_output"
IMAGE_DIR = OUTPUT_DIR / "bilder"


def main() -> int:
    ap = argparse.ArgumentParser(description="SAP-Artikel mit Swagelok-Daten (eCl@ss/UNSPSC/Bilder) anreichern")
    ap.add_argument("--limit", type=int, default=20, help="Anzahl Artikel aus OITM (0 = alle); Standard: 20")
    ap.add_argument("--price-list", type=int, default=1, help="SAP-Preisliste; Standard: 1")
    ap.add_argument("--lang", default="en", help="Sprache der Swagelok-Seite (en, de, ...); Standard: en")
    ap.add_argument("--pause", type=float, default=1.0, help="Sekunden zwischen Anfragen")
    ap.add_argument("--no-bilder", action="store_true", help="keine Bilder herunterladen")
    ap.add_argument("-o", "--output", type=Path, help="Ziel-Excel (Standard: data_output/swagelok_daten_<Zeitstempel>.xlsx)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # 1. Artikel aus SAP
    conn = get_connection()
    try:
        df_items = get_top_items(conn, limit=args.limit or None, price_list=args.price_list)
    finally:
        conn.close()
    log.info("%d Artikel aus OITM geladen", len(df_items))
    if df_items.empty:
        log.warning("Keine Artikel gefunden - nichts zu tun.")
        return 1

    # 2. Swagelok scrapen
    image_dir = None if args.no_bilder else IMAGE_DIR
    df_swagelok = scrape_items(df_items["ItemCode"].tolist(), args.lang, args.pause, image_dir)

    # 3. Anhängen (Swagelok-Name als eigene Spalte, damit er nicht mit ItemName kollidiert)
    df_swagelok = df_swagelok.rename(columns={"Artikelnummer": "ItemCode", "Name": "Swagelok_Name"})
    df_result = df_items.merge(df_swagelok, on="ItemCode", how="left")

    # 4. Excel schreiben
    output = args.output or OUTPUT_DIR / f"swagelok_daten_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    df_result.to_excel(output, index=False, sheet_name="Artikel")

    ok = int((df_result["Status"] == "OK").sum())
    log.info("Fertig: %d/%d bei Swagelok gefunden -> %s", ok, len(df_result), output)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
