{{
  config(materialized='view')
}}

/*
    int_people__employee_months
    ---------------------------
    Grain: one row per employee x month (Jan 2023 to Dec 2025) for every month
    the person was on the books at any point. Flags whether they were active at
    month end, hired in the month, or left in the month. Feeds headcount and
    attrition.
*/

with months as (
    {{ dbt_utils.date_spine(
        datepart="month",
        start_date="cast('2023-01-01' as date)",
        end_date="cast('2026-01-01' as date)"
    ) }}
),

bounds as (
    select
        cast(date_month as date)                         as month_start,
        cast({{ dbt.last_day('date_month', 'month') }} as date) as month_end
    from months
),

workers as (
    select worker_id, department, region, job_level, hire_date, termination_date, termination_type
    from {{ ref('stg_hris__workers') }}
)

select
    b.month_end,
    w.worker_id,
    w.department,
    w.region,
    w.job_level,
    (w.termination_date is null or w.termination_date > b.month_end)         as is_active_at_month_end,
    (w.hire_date between b.month_start and b.month_end)                      as is_hire,
    (w.termination_date between b.month_start and b.month_end)               as is_exit,
    case when w.termination_date between b.month_start and b.month_end
         then w.termination_type end                                         as exit_type
from bounds b
join workers w
  on w.hire_date <= b.month_end
 and (w.termination_date is null or w.termination_date >= b.month_start)
