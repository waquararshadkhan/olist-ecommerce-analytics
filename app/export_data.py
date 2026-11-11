"""Export the columns the dashboard needs from the dbt marts to a small Parquet file.

The app reads this file instead of olist.duckdb, so it can run (and be deployed)
without the raw data or dbt. Re-run after `dbt build`.

Usage:  python app/export_data.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "data"
OUT.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(ROOT / "olist.duckdb"), read_only=True)
con.execute(f"""
    COPY (
        select
            order_id,
            seller_id,
            customer_state,
            seller_state,
            category,
            purchase_month,
            order_value,
            is_multi_seller,
            is_same_state,
            distance_km,
            delivery_days,
            promised_days,
            days_vs_estimate,
            is_late,
            lateness_bucket,
            seller_handling_days,
            carrier_days,
            seller_missed_ship_limit,
            has_review,
            review_score,
            is_bad_review
        from marts.fct_orders
        where is_delivered_with_date and is_in_analysis_window
    ) TO '{(OUT / "orders.parquet").as_posix()}' (FORMAT parquet, COMPRESSION zstd)
""")
rows = con.execute(f"select count(*) from '{(OUT / 'orders.parquet').as_posix()}'").fetchone()[0]
size_mb = (OUT / "orders.parquet").stat().st_size / 1e6
print(f"app/data/orders.parquet: {rows:,} orders, {size_mb:.1f} MB")
con.close()
