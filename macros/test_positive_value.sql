{#- Generic test: fails for any row where the column is zero or negative. -#}
{% test positive_value(model, column_name) %}
select *
from {{ model }}
where {{ column_name }} <= 0
{% endtest %}
