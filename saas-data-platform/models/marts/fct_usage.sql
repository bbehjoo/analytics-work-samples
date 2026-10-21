/*
    fct_usage  —  Consumption vs entitlement
    ----------------------------------------
    Grain: one row per account x product x month (months with active entitlement).

    Joins monthly usage telemetry to the subscription entitlement in force that
    month, so consumption can be compared to what the customer is paying for.
    `utilization_pct` > 1 flags overage / expansion signal; a low utilization
    flags downsell / churn risk ahead of renewal.
*/

with entitlement as (
    select
        account_id,
        product_id,
        measurement_month as usage_month,
        entitled_units,
        arr               as entitled_arr
    from {{ ref('int_arr__account_product_month') }}
    where entitled_units > 0
),

usage as (
    select * from {{ ref('int_usage__monthly_rollup') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['e.account_id', 'e.product_id', 'e.usage_month']) }} as usage_key,
    {{ dbt_utils.generate_surrogate_key(['e.account_id']) }} as account_key,
    {{ dbt_utils.generate_surrogate_key(['e.product_id']) }} as product_key,

    e.account_id,
    e.product_id,
    e.usage_month,

    coalesce(u.consumed_units, 0)   as consumed_units,
    coalesce(u.consumed_value, 0)   as consumed_value,
    e.entitled_units,
    e.entitled_arr,

    coalesce(u.consumed_units, 0) / nullif(e.entitled_units, 0)        as utilization_pct,
    greatest(coalesce(u.consumed_units, 0) - e.entitled_units, 0)      as overage_units,
    (coalesce(u.consumed_units, 0) > e.entitled_units)                 as is_over_entitlement,
    (coalesce(u.consumed_units, 0) < 0.5 * e.entitled_units)           as is_under_utilized
from entitlement e
left join usage u
    on e.account_id = u.account_id
    and e.product_id = u.product_id
    and e.usage_month = u.usage_month
