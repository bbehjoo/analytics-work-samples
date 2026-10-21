{{
  config(materialized='view')
}}

/*
    int_arr__account_product_month
    ------------------------------
    Grain: one row per account x product x measurement month.

    Builds a monthly spine of *month-end* measurement dates, then states ARR as
    the run-rate of all subscriptions active on that date (start <= date <= end).
    The grid is densified per account x product from the first month each pair was
    active through the end of the window, with inactive months coalesced to 0 ARR,
    so that month-over-month churn and reactivation are detectable downstream.
*/

with spine as (
    {{ dbt_utils.date_spine(
        datepart="month",
        start_date="cast('2023-01-01' as date)",
        end_date="cast('2026-01-01' as date)"
    ) }}
),

measurement_months as (
    select {{ dbt.last_day('date_month', 'month') }} as measurement_month
    from spine
),

contract_lines as (
    select * from {{ ref('int_contract_lines__normalized') }}
),

-- ARR actually active on each measurement date
active as (
    select
        cl.account_id,
        cl.product_id,
        m.measurement_month,
        sum(cl.annual_recurring_amount) as arr,
        sum(cl.entitled_units)          as entitled_units
    from contract_lines cl
    inner join measurement_months m
        on m.measurement_month >= cl.subscription_start_date
        and m.measurement_month <= cl.subscription_end_date
    group by 1, 2, 3
),

-- first month each account x product pair was ever active
pairs as (
    select account_id, product_id, min(measurement_month) as first_active_month
    from active
    group by 1, 2
),

-- densify: every month from first_active_month through the window end
scaffold as (
    select
        p.account_id,
        p.product_id,
        m.measurement_month
    from pairs p
    inner join measurement_months m
        on m.measurement_month >= p.first_active_month
)

select
    s.account_id,
    s.product_id,
    s.measurement_month,
    coalesce(a.arr, 0)            as arr,
    coalesce(a.entitled_units, 0) as entitled_units
from scaffold s
left join active a
    on s.account_id = a.account_id
    and s.product_id = a.product_id
    and s.measurement_month = a.measurement_month
