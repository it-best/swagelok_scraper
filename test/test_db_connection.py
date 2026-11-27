#%%
"""Interaktiver Test der DB-Funktionen aus src/modules/db_functions.py."""

import sys
from pathlib import Path

# src/ in den Suchpfad aufnehmen (funktioniert als Skript und im Interactive Window)
_here = Path(globals().get("__file__", Path.cwd() / "_")).resolve().parent
for _p in (_here, *_here.parents):
    if (_p / "src" / "modules").is_dir():
        sys.path.insert(0, str(_p / "src"))
        break

from modules.db_functions import check_connection, get_connection, get_top_items

# %%
conn = get_connection()
try:
    user, schema, ts = check_connection(conn)
    print(f"Verbunden als {user} | Schema: {schema} | Serverzeit: {ts}")
    df_items = get_top_items(conn)
finally:
    conn.close()

df_items

# %%
