-- One row per zip-code prefix: an average point after removing exact duplicates
-- and points outside Brazil (issue 16). Analyses use state, not city (issue 18).
with points as (
    select distinct
        geolocation_zip_code_prefix as zip_code_prefix,
        geolocation_lat::double as lat,
        geolocation_lng::double as lng,
        upper(trim(geolocation_state)) as state
    from {{ source('olist', 'geolocation') }}
),

in_brazil as (
    select *
    from points
    where lat between -34 and 6
      and lng between -74 and -34
)

select
    zip_code_prefix,
    avg(lat) as lat,
    avg(lng) as lng,
    mode(state) as state,
    count(*) as point_count
from in_brazil
group by zip_code_prefix
