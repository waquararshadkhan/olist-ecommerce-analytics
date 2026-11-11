-- Orders counted in dim_customers must add up to the revenue orders in fct_orders.
select
    (select sum(order_count) from {{ ref('dim_customers') }}) as customer_orders,
    (select count(*) from {{ ref('fct_orders') }} where is_revenue_order) as revenue_orders
where (select sum(order_count) from {{ ref('dim_customers') }})
   <> (select count(*) from {{ ref('fct_orders') }} where is_revenue_order)
