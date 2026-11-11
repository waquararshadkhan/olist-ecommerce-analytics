"""Data-quality checks on the raw Olist tables (run after load_raw.py).

Prints one line per check so the findings can be reviewed and turned into
cleaning rules for the dbt staging layer.

Usage:  python scripts/check_raw_quality.py
"""
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parents[1] / "olist.duckdb"
con = duckdb.connect(str(DB_PATH), read_only=True)


def q(sql: str):
    return con.execute(sql).fetchall()


def one(sql: str):
    return con.execute(sql).fetchone()[0]


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def check(label: str, sql: str) -> None:
    print(f"{label:<62} {one(sql):>10,}")


# ---------------------------------------------------------------- 1. nulls
section("1. Missing values (columns with any nulls or blanks)")
for (table,) in q("SELECT table_name FROM information_schema.tables "
                  "WHERE table_schema = 'raw' ORDER BY 1"):
    cols = [c[0] for c in q(f"DESCRIBE raw.{table}")]
    total = one(f"SELECT count(*) FROM raw.{table}")
    for col in cols:
        n = one(f"SELECT count(*) FROM raw.{table} "
                f"WHERE {col} IS NULL OR trim({col}) = ''")
        if n:
            print(f"raw.{table}.{col:<36} {n:>9,}  ({n / total:.1%})")

# ----------------------------------------------------------- 2. uniqueness
section("2. Duplicate keys")
check("orders: duplicate order_id",
      "SELECT count(*) - count(DISTINCT order_id) FROM raw.orders")
check("customers: duplicate customer_id",
      "SELECT count(*) - count(DISTINCT customer_id) FROM raw.customers")
check("customers: rows per real person (customer_unique_id) > 1",
      "SELECT count(*) FROM (SELECT customer_unique_id FROM raw.customers "
      "GROUP BY 1 HAVING count(*) > 1)")
check("order_items: duplicate (order_id, order_item_id)",
      "SELECT count(*) - count(DISTINCT (order_id, order_item_id)) FROM raw.order_items")
check("payments: duplicate (order_id, payment_sequential)",
      "SELECT count(*) - count(DISTINCT (order_id, payment_sequential)) FROM raw.order_payments")
check("reviews: duplicate review_id",
      "SELECT count(*) - count(DISTINCT review_id) FROM raw.order_reviews")
check("reviews: duplicate (review_id, order_id)",
      "SELECT count(*) - count(DISTINCT (review_id, order_id)) FROM raw.order_reviews")
check("reviews: orders with more than one review",
      "SELECT count(*) FROM (SELECT order_id FROM raw.order_reviews "
      "GROUP BY 1 HAVING count(*) > 1)")
check("products: duplicate product_id",
      "SELECT count(*) - count(DISTINCT product_id) FROM raw.products")
check("sellers: duplicate seller_id",
      "SELECT count(*) - count(DISTINCT seller_id) FROM raw.sellers")
check("geolocation: exact duplicate rows",
      "SELECT count(*) - (SELECT count(*) FROM (SELECT DISTINCT * FROM raw.geolocation)) "
      "FROM raw.geolocation")
check("geolocation: distinct zip prefixes",
      "SELECT count(DISTINCT geolocation_zip_code_prefix) FROM raw.geolocation")

# -------------------------------------------------- 3. referential integrity
section("3. Relationships between tables")
check("orders whose customer_id is not in customers",
      "SELECT count(*) FROM raw.orders o ANTI JOIN raw.customers c USING (customer_id)")
check("order_items whose order_id is not in orders",
      "SELECT count(*) FROM raw.order_items i ANTI JOIN raw.orders o USING (order_id)")
check("order_items whose product_id is not in products",
      "SELECT count(*) FROM raw.order_items i ANTI JOIN raw.products p USING (product_id)")
check("order_items whose seller_id is not in sellers",
      "SELECT count(*) FROM raw.order_items i ANTI JOIN raw.sellers s USING (seller_id)")
check("payments whose order_id is not in orders",
      "SELECT count(*) FROM raw.order_payments p ANTI JOIN raw.orders o USING (order_id)")
check("reviews whose order_id is not in orders",
      "SELECT count(*) FROM raw.order_reviews r ANTI JOIN raw.orders o USING (order_id)")
check("orders with no items",
      "SELECT count(*) FROM raw.orders o ANTI JOIN raw.order_items i USING (order_id)")
check("orders with no payment",
      "SELECT count(*) FROM raw.orders o ANTI JOIN raw.order_payments p USING (order_id)")
check("orders with no review",
      "SELECT count(*) FROM raw.orders o ANTI JOIN raw.order_reviews r USING (order_id)")
check("product categories missing an English translation",
      "SELECT count(DISTINCT product_category_name) FROM raw.products p "
      "ANTI JOIN raw.category_translation t USING (product_category_name) "
      "WHERE p.product_category_name IS NOT NULL")
print("  untranslated categories:",
      [r[0] for r in q("SELECT DISTINCT product_category_name FROM raw.products p "
                       "ANTI JOIN raw.category_translation t USING (product_category_name) "
                       "WHERE p.product_category_name IS NOT NULL")])
check("customer zip prefixes not found in geolocation",
      "SELECT count(DISTINCT customer_zip_code_prefix) FROM raw.customers c "
      "WHERE customer_zip_code_prefix NOT IN "
      "(SELECT geolocation_zip_code_prefix FROM raw.geolocation)")
check("seller zip prefixes not found in geolocation",
      "SELECT count(DISTINCT seller_zip_code_prefix) FROM raw.sellers "
      "WHERE seller_zip_code_prefix NOT IN "
      "(SELECT geolocation_zip_code_prefix FROM raw.geolocation)")

# ---------------------------------------------------------- 4. order status
section("4. Order status")
for status, n in q("SELECT order_status, count(*) FROM raw.orders GROUP BY 1 ORDER BY 2 DESC"):
    print(f"  {status:<14} {n:>8,}")
check("delivered orders with no customer delivery date",
      "SELECT count(*) FROM raw.orders WHERE order_status = 'delivered' "
      "AND order_delivered_customer_date IS NULL")
check("non-delivered orders that have a customer delivery date",
      "SELECT count(*) FROM raw.orders WHERE order_status <> 'delivered' "
      "AND order_delivered_customer_date IS NOT NULL")
check("canceled orders that still have items",
      "SELECT count(DISTINCT order_id) FROM raw.orders JOIN raw.order_items USING (order_id) "
      "WHERE order_status = 'canceled'")

# ------------------------------------------------------------ 5. date logic
section("5. Dates")
print("  purchase date range:",
      q("SELECT min(order_purchase_timestamp), max(order_purchase_timestamp) FROM raw.orders")[0])
for label, cond in {
    "approved before purchase":
        "order_approved_at::timestamp < order_purchase_timestamp::timestamp",
    "handed to carrier before approval":
        "order_delivered_carrier_date::timestamp < order_approved_at::timestamp",
    "handed to carrier before purchase":
        "order_delivered_carrier_date::timestamp < order_purchase_timestamp::timestamp",
    "delivered to customer before handed to carrier":
        "order_delivered_customer_date::timestamp < order_delivered_carrier_date::timestamp",
    "delivered to customer before purchase":
        "order_delivered_customer_date::timestamp < order_purchase_timestamp::timestamp",
    "estimated delivery before purchase":
        "order_estimated_delivery_date::timestamp < order_purchase_timestamp::timestamp",
    "delivery took more than 60 days":
        "date_diff('day', order_purchase_timestamp::timestamp, "
        "order_delivered_customer_date::timestamp) > 60",
}.items():
    check(f"orders where {label}", f"SELECT count(*) FROM raw.orders WHERE {cond}")
check("order_items: shipping_limit_date before purchase",
      "SELECT count(*) FROM raw.order_items JOIN raw.orders USING (order_id) "
      "WHERE shipping_limit_date::timestamp < order_purchase_timestamp::timestamp")
check("reviews answered before they were created",
      "SELECT count(*) FROM raw.order_reviews "
      "WHERE review_answer_timestamp::timestamp < review_creation_date::timestamp")

section("5b. Orders per month (look for thin edge months)")
for month, n in q("SELECT strftime(order_purchase_timestamp::timestamp, '%Y-%m') m, count(*) "
                  "FROM raw.orders GROUP BY 1 ORDER BY 1"):
    print(f"  {month}  {n:>6,}")

# -------------------------------------------------------------- 6. values
section("6. Values")
check("order_items: price <= 0",
      "SELECT count(*) FROM raw.order_items WHERE price::double <= 0")
check("order_items: freight_value = 0",
      "SELECT count(*) FROM raw.order_items WHERE freight_value::double = 0")
print("  price min / median / max:",
      q("SELECT min(price::double), median(price::double), max(price::double) FROM raw.order_items")[0])
for ptype, n in q("SELECT payment_type, count(*) FROM raw.order_payments GROUP BY 1 ORDER BY 2 DESC"):
    print(f"  payment_type {ptype:<12} {n:>8,}")
check("payments: payment_value = 0",
      "SELECT count(*) FROM raw.order_payments WHERE payment_value::double = 0")
check("payments: payment_installments = 0",
      "SELECT count(*) FROM raw.order_payments WHERE payment_installments::int = 0")
check("orders where payments differ from items+freight by > R$1",
      """SELECT count(*) FROM (
           SELECT i.order_id, i.total, p.paid FROM
             (SELECT order_id, sum(price::double + freight_value::double) total
              FROM raw.order_items GROUP BY 1) i
           JOIN (SELECT order_id, sum(payment_value::double) paid
                 FROM raw.order_payments GROUP BY 1) p USING (order_id)
           WHERE abs(i.total - p.paid) > 1)""")
for score, n in q("SELECT review_score, count(*) FROM raw.order_reviews GROUP BY 1 ORDER BY 1"):
    print(f"  review_score {score}  {n:>8,}")
check("products: weight or a dimension is 0",
      "SELECT count(*) FROM raw.products WHERE product_weight_g::double = 0 "
      "OR product_length_cm::double = 0 OR product_height_cm::double = 0 "
      "OR product_width_cm::double = 0")
check("geolocation: points outside Brazil's bounding box",
      "SELECT count(*) FROM raw.geolocation WHERE "
      "geolocation_lat::double NOT BETWEEN -34 AND 6 OR "
      "geolocation_lng::double NOT BETWEEN -74 AND -34")
check("geolocation: distinct city spellings",
      "SELECT count(DISTINCT geolocation_city) FROM raw.geolocation")
check("customers: distinct city spellings",
      "SELECT count(DISTINCT customer_city) FROM raw.customers")

con.close()
