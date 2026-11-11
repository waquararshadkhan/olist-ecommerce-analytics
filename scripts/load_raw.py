"""Load the 9 raw Olist CSVs into a local DuckDB database (schema: raw).

Every column is loaded as text (all_varchar) so that nothing is silently
coerced or dropped here; type casting happens later in the dbt staging layer,
where it is visible and tested.

Usage:  python scripts/load_raw.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "olist.duckdb"

TABLES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


def main() -> None:
    missing = [f for f in TABLES.values() if not (RAW_DIR / f).exists()]
    if missing:
        raise SystemExit(
            f"Missing files in {RAW_DIR}: {missing}\n"
            "Download the dataset from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
        )

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for table, filename in TABLES.items():
        path = (RAW_DIR / filename).as_posix()
        con.execute(
            f"""
            CREATE OR REPLACE TABLE raw.{table} AS
            SELECT * FROM read_csv('{path}', header = true, all_varchar = true)
            """
        )
        rows = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
        cols = len(con.execute(f"DESCRIBE raw.{table}").fetchall())
        print(f"raw.{table:<22} {rows:>9,} rows  {cols:>2} cols")
    con.close()
    print(f"\nLoaded into {DB_PATH.name}")


if __name__ == "__main__":
    main()
