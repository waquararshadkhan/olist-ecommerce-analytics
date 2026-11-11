-- One row per product, with an English category. Missing categories become
-- 'unknown' (issue 10); zero weights/dimensions become null (issue 12).
-- Also fixes Olist's "lenght" column-name typos.
with products as (
    select * from {{ source('olist', 'products') }}
),

translation as (
    select * from {{ ref('stg_category_translation') }}
)

select
    p.product_id,
    coalesce(p.product_category_name, 'unknown') as category_name_pt,
    coalesce(t.product_category_name_english, 'unknown') as category,
    p.product_name_lenght::int as name_length,
    p.product_description_lenght::int as description_length,
    p.product_photos_qty::int as photos_count,
    nullif(p.product_weight_g::double, 0) as weight_g,
    nullif(p.product_length_cm::double, 0) as length_cm,
    nullif(p.product_height_cm::double, 0) as height_cm,
    nullif(p.product_width_cm::double, 0) as width_cm
from products p
left join translation t using (product_category_name)
