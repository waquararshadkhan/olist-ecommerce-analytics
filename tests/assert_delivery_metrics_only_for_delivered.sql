-- Delivery metrics must be blank for orders that were not delivered with a date,
-- and filled for those that were.
select order_id
from {{ ref('fct_orders') }}
where (not is_delivered_with_date and (is_late is not null or delivery_days is not null))
   or (is_delivered_with_date and (is_late is null or delivery_days is null))
