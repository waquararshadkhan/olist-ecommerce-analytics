-- One row per (review, order) pair. review_id alone repeats across orders (issue 3),
-- and some orders have several reviews (issue 4): is_latest_for_order marks the one
-- to use for order-level scores.
with typed as (
    select
        review_id || '-' || order_id as review_key,
        review_id,
        order_id,
        review_score::int as review_score,
        nullif(trim(review_comment_title), '') as comment_title,
        nullif(trim(review_comment_message), '') as comment_message,
        review_creation_date::timestamp as created_at,
        review_answer_timestamp::timestamp as answered_at
    from {{ source('olist', 'order_reviews') }}
)

select
    *,
    comment_message is not null as has_comment,
    row_number() over (
        partition by order_id
        order by created_at desc, answered_at desc, review_id
    ) = 1 as is_latest_for_order
from typed
