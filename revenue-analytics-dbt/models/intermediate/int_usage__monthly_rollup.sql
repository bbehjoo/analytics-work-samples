{{
  config(materialized='view')
}}

/*
    int_usage__monthly_rollup
    -------------------------
    Grain: one row per account x product x month. Aligns raw usage telemetry to
    the same month-end measurement date used by the ARR models so it can be joined
    to subscription entitlement in fct_usage.
*/

with usage as (
    select * from {{ ref('stg_usage__monthly') }}
)

select
    account_id,
    product_id,
    {{ dbt.last_day('usage_month', 'month') }} as usage_month,
    sum(consumed_units)  as consumed_units,
    sum(consumed_value)  as consumed_value
from usage
group by 1, 2, {{ dbt.last_day('usage_month', 'month') }}
