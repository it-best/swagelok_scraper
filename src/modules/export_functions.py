"""Export für den Unite-Katalog-Upload.

Produktgruppe: wird für jeden Artikel über die Swagelok-Series aus SAP
(``OITM.U_SWK_SeriesCd``) und die Zuordnungstabelle
``config/series_produktgruppe.csv`` bestimmt. Die Tabelle ist bearbeitbar;
Spalte ``Quelle`` zeigt, woher eine Zuordnung stammt:

* ``Katalog``   – häufigste Gruppe dieser Series im bestehenden Unite-Katalog (PKEJA)
* ``GroupCd``   – Series nicht im Katalog, abgeleitet über ``U_SWK_GroupCd``
* ``Vorschlag`` – aus den Artikeltexten abgeleitet, bitte prüfen
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SERIES_MAPPING_PATH = ROOT / "config" / "series_produktgruppe.csv"


def load_series_mapping(path: Path = SERIES_MAPPING_PATH) -> pd.DataFrame:
    """Liest die Zuordnung SeriesCd -> Produktgruppe.

    ``keep_default_na=False``, weil pandas sonst die Series "NA" als leer liest.
    """
    return pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)


def add_product_group(df_items: pd.DataFrame, path: Path = SERIES_MAPPING_PATH) -> pd.DataFrame:
    """Hängt ``Produktgruppe``, ``Produktgruppe_Name`` und ``Produktgruppe_Quelle`` an.

    Erwartet die Spalte ``SeriesCd`` (aus ``get_top_items``). Artikel ohne
    bekannte Series bekommen keine Gruppe.
    """
    mapping = load_series_mapping(path)[["SeriesCd", "Produktgruppe", "Produktgruppe_Name", "Quelle"]]
    mapping = mapping.rename(columns={"Quelle": "Produktgruppe_Quelle"})
    return df_items.merge(mapping, on="SeriesCd", how="left")


def load_catalog_groups(catalog_path: Path) -> pd.DataFrame:
    """Liest Artikel -> Produktgruppe aus einem Unite-BMEcat (.xml oder .xml.gz).

    Wird zum Neuaufbau bzw. Abgleich der Series-Zuordnung verwendet.
    Liefert ``ItemCode``, ``Produktgruppe`` (z. B. "A"), ``Produktgruppe_Name`` (z. B. "Fittings").
    """
    opener = gzip.open if catalog_path.suffix == ".gz" else open
    with opener(catalog_path, "rb") as fh:
        root = ET.parse(fh).getroot()

    group_names = {
        s.findtext("GROUP_ID"): s.findtext("GROUP_NAME")
        for s in root.iter("CATALOG_STRUCTURE")
    }
    rows = [
        (m.findtext("ART_ID"), m.findtext("CATALOG_GROUP_ID"))
        for m in root.iter("ARTICLE_TO_CATALOGGROUP_MAP")
    ]
    df = pd.DataFrame(rows, columns=["ItemCode", "Produktgruppe"]).drop_duplicates("ItemCode")
    df["Produktgruppe_Name"] = df["Produktgruppe"].map(group_names)
    return df
