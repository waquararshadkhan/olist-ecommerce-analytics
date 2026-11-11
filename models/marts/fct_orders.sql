-- One row per order: who bought, from which seller, how the delivery went, what it
-- was worth and how the customer rated it. The main table for the analysis.
--
-- Delivery metrics are only filled for delivered orders with a delivery date.
-- Stage timings (seller handling, carrier transit) are also blank for orders whose
-- timestamps are out of order (stg_orders.has_timestamp_anomaly).
with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

items as (
    select * from {{ ref('int_order_items_by_order') }}
),

payments as (
    select * from {{ ref('int_order_payments_by_order') }}
),

reviews as (
    select * from {{ ref('int_order_reviews_latest') }}
),

sellers as (
    select * from {{ ref('stg_sellers') }}
),

geo as (
    select * from {{ ref('stg_geolocation') }}
),

joined as (
    select
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        c.state as customer_state,
        o.order_status,
        o.purchased_at,
        o.purchase_month,
        o.approved_at,
        o.shipped_at,
        o.delivered_at,
        o.estimated_delivery_at,
        o.is_delivered_with_date,
        o.has_timestamp_anomaly,
        o.is_in_analysis_window,

        -- items
        coalesce(i.item_count, 0) as item_count,
        i.seller_count,
        coalesce(i.is_multi_seller, false) as is_multi_seller,
        i.primary_seller_id as seller_id,
        s.state as seller_state,
        i.primary_category as category,
        coalesce(i.items_value, 0) as items_value,
        coalesce(i.freight_value, 0) as freight_value,
        coalesce(i.order_value, 0) as order_value,
        i.shipping_limit_at,

        -- payments
        p.main_payment_type,
        p.max_installments,
        p.amount_paid,
        coalesce(p.used_voucher, false) as used_voucher,

        -- review
        r.review_score,
        r.is_bad_review,
        r.is_five_star,
        r.has_comment,
        r.review_id is not null as has_review,

        -- distance between customer and primary seller (zip-prefix centroids)
        {{ haversine_km('cg.lat', 'cg.lng', 'sg.lat', 'sg.lng') }} as distance_km
    from orders o
    left join customers c using (customer_id)
    left join items i using (order_id)
    left join payments p using (order_id)
    left join reviews r using (order_id)
    left join sellers s on s.seller_id = i.primary_seller_id
    left join geo cg on cg.zip_code_prefix = c.zip_code_prefix
    left join geo sg on sg.zip_code_prefix = s.zip_code_prefix
)

select
    *,

    -- revenue counts only orders that were not canceled or unavailable
    order_status not in ('canceled', 'unavailable') and item_count > 0 as is_revenue_order,
    customer_state = seller_state as is_same_state,

    -- delivery outcome (delivered orders with a date only)
    case when is_delivered_with_date then
        date_diff('day', purchased_at::date, delivered_at::date)
    end as delivery_days,
    case when is_delivered_with_date then
        date_diff('day', purchased_at::date, estimated_delivery_at::date)
    end as promised_days,
    case when is_delivered_with_date then
        date_diff('day', estimated_delivery_at::date, delivered_at::date)
    end as days_vs_estimate,
    case when is_delivered_with_date then
        delivered_at::date > estimated_delivery_at::date
    end as is_late,
    case
        when not is_delivered_with_date then null
        when delivered_at::date <= estimated_delivery_at::date then '0 on time'
        when date_diff('day', estimated_delivery_at::date, delivered_at::date) <= 3 then '1 late 1-3 days'
        when date_diff('day', estimated_delivery_at::date, delivered_at::date) <= 7 then '2 late 4-7 days'
        when date_diff('day', estimated_delivery_at::date, delivered_at::date) <= 14 then '3 late 8-14 days'
        else '4 late 15+ days'
    end as lateness_bucket,

    -- where the time went (clean timestamps only)
    case when is_delivered_with_date and not has_timestamp_anomaly then
        date_diff('minute', purchased_at, approved_at) / 60.0
    end as approval_hours,
    case when is_delivered_with_date and not has_timestamp_anomaly then
        date_diff('minute', approved_at, shipped_at) / 1440.0
    end as seller_handling_days,
    case when is_delivered_with_date and not has_timestamp_anomaly then
        date_diff('minute', shipped_at, delivered_at) / 1440.0
    end as carrier_days,
    case when is_delivered_with_date and not has_timestamp_anomaly then
        shipped_at > shipping_limit_at
    end as seller_missed_ship_limit
from joined
