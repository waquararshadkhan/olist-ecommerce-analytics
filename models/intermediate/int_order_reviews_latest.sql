-- One review per order: the latest one (see stg_order_reviews.is_latest_for_order).
select
    order_id,
    review_id,
    review_score,
    review_score <= 2 as is_bad_review,
    review_score = 5 as is_five_star,
    has_comment,
    comment_message,
    created_at as review_created_at
from {{ ref('stg_order_reviews') }}
where is_latest_for_order
