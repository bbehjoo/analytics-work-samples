/*
    fct_headcount_monthly
    ---------------------
    Grain: month-end x department x region. Headcount at month end, hires and
    exits in the month. Counts at this grain can describe one person (a team of
    one in one region), so the table stays private; the people_metrics models
    aggregate it and suppress small groups.
*/

with em as (
    select * from {{ ref('int_people__employee_months') }}
)

select
    month_end,
    department,
    region,
    sum(case when is_active_at_month_end then 1 else 0 end)        as headcount,
    sum(case when is_hire then 1 else 0 end)                       as hires,
    sum(case when is_exit then 1 else 0 end)                       as exits,
    sum(case when exit_type = 'Voluntary' then 1 else 0 end)       as voluntary_exits,
    sum(case when exit_type = 'Involuntary' then 1 else 0 end)     as involuntary_exits
from em
group by 1, 2, 3
