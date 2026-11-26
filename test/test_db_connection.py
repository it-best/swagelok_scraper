#%%
"""Verbindungstest zur SAP HANA DB (Zugangsdaten aus .env im Projekt-Root)."""

import os

from dotenv import find_dotenv, load_dotenv
from hdbcli import dbapi

# .env vom aktuellen Arbeitsverzeichnis aus nach oben suchen
load_dotenv(find_dotenv(usecwd=True))


def env_bool(name: str, default: str = "false") -> bool:
    """Liest eine Umgebungsvariable als Boolean."""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def get_connection() -> dbapi.Connection:
    """Baut eine Verbindung zur SAP HANA DB anhand der HANA_*-Variablen auf."""
    return dbapi.connect(
        address=os.getenv("HANA_HOST"),
        port=int(os.getenv("HANA_PORT", "30015")),
        user=os.getenv("HANA_USER"),
        password=os.getenv("HANA_PASSWORD"),
        databaseName=os.getenv("HANA_DATABASE_NAME") or None,
        currentSchema=os.getenv("HANA_SCHEMA") or None,
        encrypt=env_bool("HANA_ENCRYPT"),
        sslValidateCertificate=env_bool("HANA_SSL_VALIDATE_CERTIFICATE"),
    )


if __name__ == "__main__":
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_USER, CURRENT_SCHEMA, CURRENT_TIMESTAMP FROM DUMMY")
            user, schema, ts = cur.fetchone()
        print(f"Verbunden als {user} | Schema: {schema} | Serverzeit: {ts}")
    finally:
        conn.close()

# %%
import pandas as pd


def get_top_items(conn: dbapi.Connection, limit: int = 10, price_list: int = 1) -> pd.DataFrame:
    """Holt die ersten `limit` Artikel aus OITM inkl. Preis aus Preisliste `price_list` (ITM1)."""
    query = f"""
        SELECT
            T0."ItemCode",
            T0."ItemName",
            T1."Price",
            T1."Currency"
        FROM "OITM" T0
        LEFT JOIN "ITM1" T1
            ON  T1."ItemCode"  = T0."ItemCode"
            AND T1."PriceList" = {int(price_list)}
        WHERE T1."Price" IS NOT NULL AND T1."Price" > 0
            AND T0."validFor" = 'Y'
            AND T0."U_SWK_FulfillmentStrategyCode" LIKE '%MTS%'
    """
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=columns)
    # HANA liefert Decimal -> für Berechnungen in float umwandeln
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    return df


conn = get_connection()
try:
    df_items = get_top_items(conn)
finally:
    conn.close()

df_items

# %%
