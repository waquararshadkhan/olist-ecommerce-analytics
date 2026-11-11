-- One row per order that has items: totals, plus the "primary" seller and category.
-- About 1% of orders contain items from more than one seller; the primary seller is
-- the one with the highest item value in the order, and is_multi_seller flags them.
with items as (
    select
        i.*,
        p.category
    from {{ ref('stg_order_items') }} i
    left join {{ ref('stg_products') }} p using (product_id)
),

seller_value as (
    select
        order_id,
        seller_id,
        sum(item_total) as seller_value,
        row_number() over (
            partition by order_id
            order by sum(item_total) desc, seller_id
        ) as seller_rank
    from items
    group by order_id, seller_id
),

category_value as (
    select
        order_id,
        category,
        row_number() over (
            partition by order_id
            order by sum(item_total) desc, category
        ) as category_rank
    from items
    group by order_id, category
),

totals as (
    select
        order_id,
        count(*) as item_count,
        count(distinct product_id) as product_count,
        count(distinct seller_id) as seller_count,
        sum(price) as items_value,
        sum(freight_value) as freight_value,
        sum(item_total) as order_value,
        max(shipping_limit_at) as shipping_limit_at
    from items
    group by order_id
)

select
    t.*,
    t.seller_count > 1 as is_multi_seller,
    s.seller_id as primary_seller_id,
    c.category as primary_category
from totals t
join seller_value s on s.order_id = t.order_id and s.seller_rank = 1
join category_value c on c.order_id = t.order_id and c.category_rank = 1
