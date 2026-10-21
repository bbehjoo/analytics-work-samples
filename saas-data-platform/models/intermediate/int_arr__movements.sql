{{
  config(materialized='view')
}}

/*
    int_arr__movements
    ------------------
    Grain: one row per account x product x measurement month (active months and
    the month a pair churns to zero).

    The ARR waterfall engine. For each account x product it compares this month's
    ARR to the prior month and classifies the change into a revenue category, then
    splits the change into signed movement buckets so that, for any month:

        sum(ending_arr) = sum(beginning_arr)
                        + sum(new_logo + cross_sell + upsell + downgrade + churn)

    Category logic (account/product context decides new_logo vs cross_sell vs
    reactivation, the latter folded into new_logo as a win-back):
        prev = 0, now > 0  -> new_logo  (account had no prior ARR)
                           -> cross_sell (account active, product is new)
                           -> new_logo  (win-back of a previously churned product)
        now > prev > 0     -> upsell
        0 < now < prev     -> downgrade
        prev > 0, now = 0  -> churn
        now = prev > 0     -> scheduled (contracted run-rate, unchanged)
*/

with apm as (
    select * from {{ ref('int_arr__account_product_month') }}
),

-- account-level context: did the account have any ARR in a *prior* month?
account_month as (
    select
        account_id,
        measurement_month,
        sum(arr) as account_arr
    from apm
    group by 1, 2
),

account_context as (
    select
        account_id,
        measurement_month,
        coalesce(
            max(case when account_arr > 0 then 1 else 0 end) over (
                partition by account_id
                order by measurement_month
                rows between unbounded preceding and 1 preceding
            ), 0
        ) as account_active_before
    from account_month
),

with_lag as (
    select
        apm.account_id,
        apm.product_id,
        apm.measurement_month,
        apm.arr,
        apm.entitled_units,
        coalesce(
            lag(apm.arr) over (
                partition by apm.account_id, apm.product_id
                order by apm.measurement_month
            ), 0
        ) as prior_arr,
        coalesce(
            max(case when apm.arr > 0 then 1 else 0 end) over (
                partition by apm.account_id, apm.product_id
                order by apm.measurement_month
                rows between unbounded preceding and 1 preceding
            ), 0
        ) as product_active_before
    from apm
),

classified as (
    select
        wl.*,
        ac.account_active_before,
        wl.arr - wl.prior_arr as arr_change,
        case
            when wl.arr > 0 and wl.prior_arr = 0 and ac.account_active_before = 0 then 'new_logo'
            when wl.arr > 0 and wl.prior_arr = 0 and wl.product_active_before = 0 then 'cross_sell'
            when wl.arr > 0 and wl.prior_arr = 0 then 'new_logo'           -- win-back
            when wl.arr > wl.prior_arr and wl.prior_arr > 0 then 'upsell'
            when wl.arr < wl.prior_arr and wl.arr > 0 then 'downgrade'
            when wl.prior_arr > 0 and wl.arr = 0 then 'churn'
            when wl.arr = wl.prior_arr and wl.arr > 0 then 'scheduled'
            else 'inactive'
        end as revenue_category
    from with_lag wl
    inner join account_context ac
        on wl.account_id = ac.account_id
        and wl.measurement_month = ac.measurement_month
)

select
    account_id,
    product_id,
    measurement_month,
    prior_arr            as beginning_arr,
    arr                  as ending_arr,
    arr_change,
    entitled_units,
    revenue_category,
    case when revenue_category in ('new_logo')   then arr_change else 0 end as new_logo_arr,
    case when revenue_category = 'cross_sell'     then arr_change else 0 end as cross_sell_arr,
    case when revenue_category = 'upsell'         then arr_change else 0 end as upsell_arr,
    case when revenue_category = 'downgrade'      then arr_change else 0 end as downgrade_arr,
    case when revenue_category = 'churn'          then arr_change else 0 end as churn_arr,
    case when revenue_category = 'scheduled'      then ending_arr else 0 end as scheduled_arr
from classified
where revenue_category <> 'inactive'
