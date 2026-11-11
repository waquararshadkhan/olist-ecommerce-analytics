-- fct_orders must keep every order (no row lost or duplicated by joins).
select
    (select count(*) from {{ ref('fct_orders') }}) as fct_rows,
    (select count(*) from {{ ref('stg_orders') }}) as stg_rows
where (select count(*) from {{ ref('fct_orders') }})
   <> (select count(*) from {{ ref('stg_orders') }})
