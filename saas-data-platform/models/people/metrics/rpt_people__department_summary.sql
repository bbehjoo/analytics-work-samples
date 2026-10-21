/*
    rpt_people__department_summary
    ------------------------------
    One row per department, plus an "All departments" row, as of the HR snapshot
    date: headcount, trailing twelve-month attrition, and pay against band. Safe
    to share: any department with fewer than var('min_group_size') people shows
    is_suppressed = true and no numbers, because a figure about two people is a
    figure about a person.
*/

{% set as_of = "cast('" ~ var('people_as_of') ~ "' as date)" %}

with active as (
    select department, compa_ratio, base_salary
    from {{ ref('dim_employee') }}
    where is_active
),

current_state as (
    select department, count(*) as n, avg(compa_ratio) as avg_compa_ratio, avg(base_salary) as avg_base_salary
    from active
    group by 1
    union all
    select 'All departments', count(*), avg(compa_ratio), avg(base_salary)
    from active
),

monthly as (
    select month_end, department,
           sum(headcount) as headcount, sum(exits) as exits, sum(voluntary_exits) as voluntary_exits
    from {{ ref('fct_headcount_monthly') }}
    where month_end > {{ dbt.dateadd('month', -12, as_of) }}
      and month_end <= {{ as_of }}
    group by 1, 2
),

ttm as (
    select department, avg(headcount) as avg_headcount, sum(exits) as exits, sum(voluntary_exits) as voluntary_exits
    from monthly
    group by 1
    union all
    select 'All departments', avg(headcount), sum(exits), sum(voluntary_exits)
    from (
        select month_end, sum(headcount) as headcount, sum(exits) as exits, sum(voluntary_exits) as voluntary_exits
        from monthly
        group by 1
    ) company
)

select
    a.department,
    a.n < {{ var('min_group_size') }}                                        as is_suppressed,
    {{ suppress('a.n', 'a.n') }}                                             as headcount,
    {{ suppress('a.n', 'round(t.exits / t.avg_headcount, 3)') }}             as attrition_rate_ttm,
    {{ suppress('a.n', 'round(t.voluntary_exits / t.avg_headcount, 3)') }}   as voluntary_attrition_rate_ttm,
    {{ suppress('a.n', 'round(a.avg_compa_ratio, 3)') }}                     as avg_compa_ratio,
    {{ suppress('a.n', salary_band('a.avg_base_salary')) }}                  as avg_base_pay_band
from current_state a
left join ttm t on a.department = t.department
