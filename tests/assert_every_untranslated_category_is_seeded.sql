-- Every Portuguese category used by a product must have an English name.
-- Fails if Olist data contains a category missing from both the source
-- translation table and seeds/category_translation_missing.csv.
select distinct p.category_name_pt
from {{ ref('stg_products') }} p
where p.category = 'unknown'
  and p.category_name_pt <> 'unknown'
