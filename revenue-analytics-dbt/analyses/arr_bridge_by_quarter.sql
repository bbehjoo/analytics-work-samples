/*
    arr_bridge_by_quarter
    ---------------------
    The company ARR waterfall, rolled up to quarter: how beginning ARR turns into
    ending ARR via new logo, expansion (upsell + cross-sell), and contraction
    (downgrade + churn). This is the single most important GTM view — it answers
    "where did growth come from, and where are we leaking?".

    `dbt compile` this (or paste into any SQL client) to run it.
*/
with quarterly as (
    select
        cast(extract(year from measurement_month) as integer) as fiscal_year,
        'Q' || cast(extract(quarter from measurement_month) as integer) as fiscal_quarter,
        max(measurement_month) as quarter_end
    from {{ ref('fct_arr') }}
    group by 1, 2
),

month_end_arr as (
    -- ending ARR at each quarter-end snapshot
    select
        q.fiscal_year,
        q.fiscal_quarter,
        sum(f.ending_arr) as ending_arr
    from {{ ref('fct_arr') }} f
    inner join quarterly q on f.measurement_month = q.quarter_end
    group by 1, 2
),

movements as (
    select
        cast(extract(year from measurement_month) as integer) as fiscal_year,
        'Q' || cast(extract(quarter from measurement_month) as integer) as fiscal_quarter,
        sum(new_logo_arr)    as new_logo_arr,
        sum(cross_sell_arr)  as cross_sell_arr,
        sum(upsell_arr)      as upsell_arr,
        sum(downgrade_arr)   as downgrade_arr,
        sum(churn_arr)       as churn_arr,
        sum(arr_change)      as net_new_arr
    from {{ ref('fct_arr') }}
    group by 1, 2
)

select
    m.fiscal_year,
    m.fiscal_quarter,
    m.new_logo_arr,
    m.cross_sell_arr,
    m.upsell_arr,
    (m.upsell_arr + m.cross_sell_arr) as expansion_arr,
    m.downgrade_arr,
    m.churn_arr,
    m.net_new_arr,
    e.ending_arr
from movements m
left join month_end_arr e
    on m.fiscal_year = e.fiscal_year and m.fiscal_quarter = e.fiscal_quarter
order by m.fiscal_year, m.fiscal_quarter
