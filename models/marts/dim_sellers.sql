-- One row per seller: volume, revenue and delivery performance, so late deliveries
-- and bad reviews can be traced to specific sellers. Orders are attributed to their
-- primary seller (see int_order_items_by_order).
with orders as (
    select *
    from {{ ref('fct_orders') }}
    where is_revenue_order
),

items as (
    select seller_id, count(*) as items_sold, sum(item_total) as item_revenue
    from {{ ref('stg_order_items') }} i
    join {{ ref('stg_orders') }} o using (order_id)
    where o.order_status not in ('canceled', 'unavailable')
    group by seller_id
),

perf as (
    select
        seller_id,
        count(*) as order_count,
        count(distinct customer_unique_id) as customer_count,
        min(purchased_at) as first_sale_at,
        max(purchased_at) as last_sale_at,
        mode(category) as main_category,

        count(*) filter (where is_delivered_with_date) as delivered_orders,
        avg(is_late::int) as late_rate,
        avg(delivery_days) as avg_delivery_days,
        avg(seller_handling_days) as avg_handling_days,
        avg(seller_missed_ship_limit::int) as missed_ship_limit_rate,
        avg(distance_km) as avg_distance_km,

        count(review_score) as reviewed_orders,
        avg(review_score) as avg_review_score,
        avg(is_bad_review::int) as bad_review_rate
    from orders
    group by seller_id
)

select
    s.seller_id,
    s.state,
    s.city,
    coalesce(p.order_count, 0) as order_count,
    coalesce(i.items_sold, 0) as items_sold,
    coalesce(i.item_revenue, 0) as revenue,
    p.customer_count,
    p.first_sale_at,
    p.last_sale_at,
    p.main_category,
    p.delivered_orders,
    p.late_rate,
    p.avg_delivery_days,
    p.avg_handling_days,
    p.missed_ship_limit_rate,
    p.avg_distance_km,
    p.reviewed_orders,
    p.avg_review_score,
    p.bad_review_rate,
    -- small sellers have noisy rates; analysis filters on this
    coalesce(p.delivered_orders, 0) >= 30 as has_enough_orders
from {{ ref('stg_sellers') }} s
left join perf p using (seller_id)
left join items i using (seller_id)
