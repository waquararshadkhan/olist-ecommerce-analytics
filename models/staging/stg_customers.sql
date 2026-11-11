-- One row per customer_id (= one per order). customer_unique_id is the real person
-- and is what all repeat-purchase analysis must use (issue 1).
select
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix as zip_code_prefix,
    lower(trim(customer_city)) as city,
    upper(trim(customer_state)) as state
from {{ source('olist', 'customers') }}
