/*
    fct_arr  —  Annual Recurring Revenue (bookings / billings run-rate)
    -----------------------------------------------------------------
    Grain: one row per account x product x month-end measurement date.

    The recurring run-rate fact and ARR waterfall. `ending_arr` is the run-rate
    on the measurement date; the signed movement columns
    (new_logo / cross_sell / upsell / downgrade / churn / scheduled) sum to the
    change from `beginning_arr`, so a company ARR bridge is just a roll-up by
    month. ARR is recurring-only (no one-time fees). NRR/GRR are derived from
    the movement columns against a cohort's beginning ARR.
*/

with movements as (
    select * from {{ ref('int_arr__movements') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['account_id', 'product_id', 'measurement_month']) }} as arr_key,
    {{ dbt_utils.generate_surrogate_key(['account_id']) }} as account_key,
    {{ dbt_utils.generate_surrogate_key(['product_id']) }} as product_key,

    account_id,
    product_id,
    measurement_month,
    revenue_category,

    beginning_arr,
    ending_arr,
    arr_change,
    entitled_units,

    new_logo_arr,
    cross_sell_arr,
    upsell_arr,
    downgrade_arr,
    churn_arr,
    scheduled_arr
from movements
