-- Proof test: for every measurement month the ARR waterfall must balance, i.e.
--   sum(ending_arr) = sum(beginning_arr) + sum(all movement buckets)
-- Returns any month that fails to reconcile (expected: 0 rows).
with monthly as (
    select
        measurement_month,
        sum(ending_arr) as ending_arr,
        sum(beginning_arr)
            + sum(new_logo_arr + cross_sell_arr + upsell_arr + downgrade_arr + churn_arr)
            as reconstructed_ending_arr
    from {{ ref('fct_arr') }}
    group by 1
)

select *
from monthly
where abs(ending_arr - reconstructed_ending_arr) > 0.01
