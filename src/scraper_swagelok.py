"""Swagelok-Produktdaten-Scraper.

Liest pro Artikelnummer die Produktseite
``https://products.swagelok.com/{lang}/p/{Artikelnummer}`` und extrahiert:

* Produktname und kanonische URL
* alle eCl@ss- und UNSPSC-Codes (alle angebotenen Versionen)
* Bild-URLs (Standard- und Zoom-Variante), optional mit Download

Nur Python-Standardbibliothek, keine zusätzlichen Pakete nötig.

Beispiele:
    python swagelok_scraper.py 177-13K-R4-A SS-400-6
    python swagelok_scraper.py -i artikel.txt -o ergebnis.csv --bilder bilder
    python swagelok_scraper.py -i artikel.csv --lang de --pause 1.5
"""

from __future__ import annotations

import argparse
import csv
import html
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://products.swagelok.com/{lang}/p/{part}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
PLACEHOLDER = "placeholder.png"

# Spezifikationszeile: <td><b>Label</b></td> <td>Wert</td>
RE_SPEC_ROW = re.compile(
    r"<td>\s*<b>(?P<label>[^<]+)</b>\s*</td>\s*<td>(?P<value>.*?)</td>",
    re.S,
)
RE_NAME = re.compile(r'<h1 class="s-product-detail__name">(.*?)</h1>', re.S)
RE_ZOOM_IMG = re.compile(r'data-zoom-image="([^"]+)"')
RE_IMG = re.compile(r'data-src="(https://www\.swagelok\.com/assets/images/product_images/[^"]+)"')
RE_CLASS_LABEL = re.compile(r"^(eClass|UNSPSC)\s*\(([^)]+)\)$", re.I)

log = logging.getLogger("swagelok_scraper")


def clean(text: str) -> str:
    """Entfernt HTML-Tags, dekodiert Entities und normalisiert Leerraum."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch(url: str, retries: int = 3, timeout: int = 30) -> tuple[str, str]:
    """Lädt eine Seite und liefert (finale URL, HTML).

    Raises:
        urllib.error.HTTPError: Bei 4xx (kein Retry) oder nach letztem Versuch.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.geturl(), resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 or attempt == retries:
                raise
            log.warning("HTTP %s bei %s, Versuch %d/%d", exc.code, url, attempt, retries)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise
            log.warning("Netzwerkfehler bei %s (%s), Versuch %d/%d", url, exc, attempt, retries)
        time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def parse_product(part: str, final_url: str, page: str) -> dict:
    """Extrahiert Name, Klassifikationen und Bilder aus einer Produktseite."""
    # Die Seite enthält die Spezifikationen doppelt (Bildschirm + Druckansicht);
    # erstes Vorkommen gewinnt.
    classes: dict[str, str] = {}
    for m in RE_SPEC_ROW.finditer(page):
        label = clean(m.group("label"))
        lm = RE_CLASS_LABEL.match(label)
        if lm:
            key = f"{'eClass' if lm.group(1).lower() == 'eclass' else 'UNSPSC'} {lm.group(2)}"
            classes.setdefault(key, clean(m.group("value")))

    name_match = RE_NAME.search(page)
    zoom = [u for u in dict.fromkeys(RE_ZOOM_IMG.findall(page)) if PLACEHOLDER not in u]
    std = [u for u in dict.fromkeys(RE_IMG.findall(page)) if PLACEHOLDER not in u]

    return {
        "Artikelnummer": part,
        "Status": "OK",
        "Name": clean(name_match.group(1)) if name_match else "",
        "URL": final_url,
        "Bild": " | ".join(std),
        "Bild_Zoom": " | ".join(zoom),
        **classes,
    }


def image_filename(url: str) -> str:
    """Dateiname eines Bildes ohne Query-String (z. B. 177-13K-R4-B.jpg)."""
    return Path(urllib.parse.urlparse(url).path).name


def download_images(row: dict, target: Path) -> list[str]:
    """Lädt die Zoom-Bilder (Fallback: Standardbilder) nach ``target``.

    Dateiname: ``{Artikelnummer}[_n].{ext}``; mehrere Artikel können dasselbe
    Swagelok-Bild teilen, daher wird nach Artikelnummer benannt.
    """
    urls = [u for u in (row["Bild_Zoom"] or row["Bild"]).split(" | ") if u]
    saved = []
    target.mkdir(parents=True, exist_ok=True)
    safe_part = re.sub(r'[\\/:*?"<>|]', "_", row["Artikelnummer"])
    for i, url in enumerate(urls):
        ext = Path(image_filename(url)).suffix or ".jpg"
        dest = target / f"{safe_part}{'' if i == 0 else f'_{i + 1}'}{ext}"
        if dest.exists():
            saved.append(dest.name)
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                dest.write_bytes(resp.read())
            saved.append(dest.name)
        except (urllib.error.URLError, TimeoutError) as exc:
            log.error("Bild-Download fehlgeschlagen %s: %s", url, exc)
    return saved


def read_parts(path: Path) -> list[str]:
    """Liest Artikelnummern aus TXT/CSV (erste Spalte, Kopfzeile wird erkannt)."""
    text = path.read_text(encoding="utf-8-sig")
    parts = []
    for line in text.splitlines():
        first = re.split(r"[;,\t]", line, maxsplit=1)[0].strip().strip('"')
        if first and first.lower() not in {"artikelnummer", "artikel", "part", "partnumber", "sku"}:
            parts.append(first)
    return list(dict.fromkeys(parts))


def sort_class_columns(cols: set[str]) -> list[str]:
    """Sortiert 'eClass 10.1' / 'UNSPSC 4.03' nach System und Versionsnummer."""
    def key(c: str):
        system, version = c.split(" ", 1)
        nums = tuple(int(x) for x in re.findall(r"\d+", version))
        return (system.lower() != "eclass", nums)
    return sorted(cols, key=key)


def main() -> int:
    ap = argparse.ArgumentParser(description="Swagelok eCl@ss/UNSPSC/Bild-Scraper")
    ap.add_argument("parts", nargs="*", help="Artikelnummern direkt angeben")
    ap.add_argument("-i", "--input", type=Path, help="TXT/CSV mit Artikelnummern (erste Spalte)")
    ap.add_argument("-o", "--output", type=Path, default=Path("swagelok_daten.csv"))
    ap.add_argument("--lang", default="en", help="Sprache der Seite (en, de, ...); Standard: en")
    ap.add_argument("--bilder", type=Path, help="Ordner für Bild-Downloads (ohne: kein Download)")
    ap.add_argument("--pause", type=float, default=1.0, help="Sekunden zwischen Anfragen")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parts = list(args.parts)
    if args.input:
        parts += read_parts(args.input)
    parts = list(dict.fromkeys(p.strip() for p in parts if p.strip()))
    if not parts:
        ap.error("Keine Artikelnummern angegeben (Argumente oder --input).")

    rows: list[dict] = []
    for n, part in enumerate(parts, 1):
        url = BASE_URL.format(lang=args.lang, part=urllib.parse.quote(part, safe=""))
        try:
            final_url, page = fetch(url)
            # Unbekannte Artikel landen nicht auf einer /p/-Seite
            if "/p/" not in final_url or "s-product-detail__name" not in page:
                rows.append({"Artikelnummer": part, "Status": "nicht gefunden", "URL": final_url})
                log.warning("[%d/%d] %s: nicht gefunden", n, len(parts), part)
            else:
                row = parse_product(part, final_url, page)
                if args.bilder:
                    row["Bilddateien"] = " | ".join(download_images(row, args.bilder))
                rows.append(row)
                n_cls = sum(1 for k in row if k.startswith(("eClass", "UNSPSC")))
                log.info("[%d/%d] %s: %d Klassifikationen, Bild: %s",
                         n, len(parts), part, n_cls, "ja" if row["Bild"] else "nein")
        except urllib.error.HTTPError as exc:
            status = "nicht gefunden" if exc.code == 404 else f"HTTP {exc.code}"
            rows.append({"Artikelnummer": part, "Status": status, "URL": url})
            log.warning("[%d/%d] %s: %s", n, len(parts), part, status)
        except (urllib.error.URLError, TimeoutError) as exc:
            rows.append({"Artikelnummer": part, "Status": f"Fehler: {exc}", "URL": url})
            log.error("[%d/%d] %s: %s", n, len(parts), part, exc)
        if n < len(parts):
            time.sleep(args.pause)

    class_cols = sort_class_columns(
        {k for r in rows for k in r if k.startswith(("eClass ", "UNSPSC "))})
    fields = ["Artikelnummer", "Status", "Name", *class_cols, "Bild", "Bild_Zoom"]
    if args.bilder:
        fields.append("Bilddateien")
    fields.append("URL")

    # utf-8-sig + Semikolon: öffnet sich in deutschem Excel direkt korrekt
    with args.output.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r["Status"] == "OK")
    log.info("Fertig: %d/%d gefunden -> %s", ok, len(rows), args.output.resolve())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
