-- One row per order that has payments. The main payment type is the one with the
-- largest value. Revenue still comes from items; this is for payment behaviour.
with ranked as (
    select
        *,
        row_number() over (
            partition by order_id
            order by payment_value desc, payment_sequence
        ) as value_rank
    from {{ ref('stg_order_payments') }}
)

select
    order_id,
    count(*) as payment_count,
    sum(payment_value) as amount_paid,
    max(installments) as max_installments,
    max(case when value_rank = 1 then payment_type end) as main_payment_type,
    bool_or(payment_type = 'voucher') as used_voucher,
    bool_or(is_suspect_payment) as has_suspect_payment
from ranked
group by order_id
