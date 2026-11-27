"""Scraping-Funktionen für Swagelok-Produktseiten.

Liest pro Artikelnummer die Produktseite
``https://products.swagelok.com/{lang}/p/{Artikelnummer}`` und extrahiert:

* Produktname und kanonische URL
* alle eCl@ss- und UNSPSC-Codes (alle angebotenen Versionen)
* Bild-URLs (Standard- und Zoom-Variante), optional mit Download
"""

from __future__ import annotations

import html
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

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


def product_url(part: str, lang: str = "en") -> str:
    """Produkt-URL zu einer Artikelnummer.

    Swagelok erwartet "/" doppelt kodiert (``%252F``), z. B.
    SS-CHVCR4-KZ-1/3 -> .../p/SS-CHVCR4-KZ-1%252F3
    """
    encoded = urllib.parse.quote(part, safe="").replace("%2F", "%252F")
    return BASE_URL.format(lang=lang, part=encoded)


def scrape_part(part: str, lang: str = "en", image_dir: Path | None = None) -> dict:
    """Scrapt eine Artikelnummer und liefert eine Ergebniszeile.

    Mit ``image_dir`` werden die Bilder dorthin geladen und die Dateinamen
    in ``Bilddateien`` eingetragen. Fehler landen in ``Status``, es wird
    keine Exception geworfen.
    """
    url = product_url(part, lang)
    try:
        final_url, page = fetch(url)
    except urllib.error.HTTPError as exc:
        status = "nicht gefunden" if exc.code == 404 else f"HTTP {exc.code}"
        return {"Artikelnummer": part, "Status": status, "URL": url}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"Artikelnummer": part, "Status": f"Fehler: {exc}", "URL": url}

    # Unbekannte Artikel landen nicht auf einer /p/-Seite
    if "/p/" not in final_url or "s-product-detail__name" not in page:
        return {"Artikelnummer": part, "Status": "nicht gefunden", "URL": final_url}

    row = parse_product(part, final_url, page)
    if image_dir:
        row["Bilddateien"] = " | ".join(download_images(row, image_dir))
    return row


def scrape_items(
    item_codes: list[str],
    lang: str = "en",
    pause: float = 1.0,
    image_dir: Path | None = None,
    workers: int = 4,
) -> pd.DataFrame:
    """Scrapt alle ItemCodes parallel und liefert die Ergebnisse als DataFrame.

    ``workers`` Anfragen laufen gleichzeitig; jeder Worker wartet nach einem
    Artikel ``pause`` Sekunden, um den Server nicht zu überlasten.
    Die Reihenfolge der Zeilen entspricht ``item_codes``.
    """
    def task(part: str) -> dict:
        row = scrape_part(part, lang=lang, image_dir=image_dir)
        time.sleep(pause)
        return row

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(task, part): part for part in item_codes}
        for n, future in enumerate(as_completed(futures), 1):
            part = futures[future]
            row = future.result()
            results[part] = row
            n_cls = sum(1 for k in row if k.startswith(("eClass ", "UNSPSC ")))
            log.info("[%d/%d] %s: %s, %d Klassifikationen, Bilder: %s",
                     n, len(item_codes), part, row["Status"], n_cls, row.get("Bilddateien") or "-")

    rows = [results[part] for part in item_codes]

    # Spalten sortieren: Status, Name, Klassifikationen (nach Version), Bilder, URL
    class_cols = sort_class_columns({k for r in rows for k in r if k.startswith(("eClass ", "UNSPSC "))})
    cols = ["Artikelnummer", "Status", "Name", *class_cols, "Bild", "Bild_Zoom", "Bilddateien", "URL"]
    return pd.DataFrame(rows).reindex(columns=cols)
