-- Total order value in fct_orders must equal the sum of item price + freight.
-- Fails (returns a row) if the joins dropped or duplicated anything.
with fct as (
    select sum(order_value) as total from {{ ref('fct_orders') }}
),

items as (
    select sum(item_total) as total from {{ ref('stg_order_items') }}
)

select fct.total as fct_total, items.total as items_total
from fct, items
where abs(fct.total - items.total) > 0.01
