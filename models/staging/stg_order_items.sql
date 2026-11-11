-- One row per item line in an order. Revenue is built from price + freight here,
-- not from payments (issue 14).
select
    order_id || '-' || order_item_id as order_item_key,
    order_id,
    order_item_id::int as order_item_number,
    product_id,
    seller_id,
    shipping_limit_date::timestamp as shipping_limit_at,
    price::decimal(10, 2) as price,
    freight_value::decimal(10, 2) as freight_value,
    (price::decimal(10, 2) + freight_value::decimal(10, 2)) as item_total
from {{ source('olist', 'order_items') }}
