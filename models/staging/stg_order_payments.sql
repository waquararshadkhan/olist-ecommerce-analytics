-- One row per payment within an order. Odd values are flagged, not removed (issue 13).
with typed as (
    select
        order_id || '-' || payment_sequential as payment_key,
        order_id,
        payment_sequential::int as payment_sequence,
        payment_type,
        payment_installments::int as installments,
        payment_value::decimal(10, 2) as payment_value
    from {{ source('olist', 'order_payments') }}
)

select
    *,
    (payment_type = 'not_defined' or payment_value = 0 or installments = 0)
        as is_suspect_payment
from typed
