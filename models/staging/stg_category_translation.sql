-- Portuguese -> English category names: the 71 from Olist plus the 2 it is
-- missing, added in seeds/category_translation_missing.csv (issue 11).
select product_category_name, product_category_name_english
from {{ source('olist', 'category_translation') }}

union all

select product_category_name, product_category_name_english
from {{ ref('category_translation_missing') }}
