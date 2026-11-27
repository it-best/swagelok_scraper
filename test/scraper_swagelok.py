#%%
"""Interaktiver Test der Scraping-Funktionen aus src/modules/scraping_functions.py."""

import sys
from pathlib import Path

# src/ in den Suchpfad aufnehmen (funktioniert als Skript und im Interactive Window)
_here = Path(globals().get("__file__", Path.cwd() / "_")).resolve().parent
for _p in (_here, *_here.parents):
    if (_p / "src" / "modules").is_dir():
        sys.path.insert(0, str(_p / "src"))
        break

from modules.scraping_functions import fetch, parse_product, product_url

# %%
part = "SS-400-6"
url = product_url(part)
final_url, page = fetch(url)
row = parse_product(part, final_url, page)
row

# %%
