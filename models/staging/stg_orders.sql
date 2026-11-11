-- One row per order. Casts timestamps and flags the timestamp problems
-- found in docs/data_quality.md (issues 5-7, 9) instead of deleting rows.
with source as (
    select * from {{ source('olist', 'orders') }}
),

typed as (
    select
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp::timestamp      as purchased_at,
        order_approved_at::timestamp             as approved_at,
        order_delivered_carrier_date::timestamp  as shipped_at,
        order_delivered_customer_date::timestamp as delivered_at,
        order_estimated_delivery_date::timestamp as estimated_delivery_at
    from source
)

select
    *,
    date_trunc('month', purchased_at)::date as purchase_month,

    -- Delivered and both dates known: the only orders used for on-time analysis.
    (order_status = 'delivered' and delivered_at is not null) as is_delivered_with_date,

    -- Out-of-order timestamps (issues 6-7): exclude from stage-level timings.
    coalesce(
        shipped_at < approved_at
        or shipped_at < purchased_at
        or delivered_at < shipped_at,
        false
    ) as has_timestamp_anomaly,

    -- Sep-Dec 2016 and Sep-Oct 2018 have too few orders for trends (issue 9).
    (purchased_at >= '2017-01-01' and purchased_at < '2018-09-01') as is_in_analysis_window
from typed
