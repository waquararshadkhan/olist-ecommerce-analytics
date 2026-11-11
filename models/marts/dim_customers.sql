-- One row per real customer (customer_unique_id), built from their orders.
-- first_order_* columns describe the customer's first experience, which the
-- analysis uses to test whether a bad first delivery stops people coming back.
with orders as (
    select *
    from {{ ref('fct_orders') }}
    where is_revenue_order
),

ranked as (
    select
        *,
        row_number() over (partition by customer_unique_id order by purchased_at, order_id) as order_rank
    from orders
),

first_order as (
    select * from ranked where order_rank = 1
),

second_order as (
    select * from ranked where order_rank = 2
),

totals as (
    select
        customer_unique_id,
        count(*) as order_count,
        sum(order_value) as lifetime_value,
        min(purchased_at) as first_order_at,
        max(purchased_at) as last_order_at,
        count(distinct category) as category_count
    from orders
    group by customer_unique_id
)

select
    t.customer_unique_id,
    f.customer_state as state,
    t.order_count,
    t.order_count > 1 as is_repeat_customer,
    t.lifetime_value,
    t.first_order_at,
    t.last_order_at,
    t.category_count,
    date_diff('day', f.purchased_at, s.purchased_at) as days_to_second_order,

    -- the first experience
    f.order_id as first_order_id,
    f.purchase_month as first_order_month,
    f.category as first_order_category,
    f.order_value as first_order_value,
    f.is_late as first_order_was_late,
    f.lateness_bucket as first_order_lateness_bucket,
    f.delivery_days as first_order_delivery_days,
    f.review_score as first_order_review_score,
    f.is_in_analysis_window as first_order_in_analysis_window
from totals t
join first_order f using (customer_unique_id)
left join second_order s using (customer_unique_id)
