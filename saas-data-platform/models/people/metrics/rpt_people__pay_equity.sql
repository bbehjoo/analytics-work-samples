/*
    rpt_people__pay_equity
    ----------------------
    One row per job level x gender among current employees, plus an "All" row
    per gender: how pay compares with the band midpoint (compa-ratio), the gap to
    men at the same level, and what it would cost to close it.

    Comparing within level and against the same band (bands are set by level and
    region) makes the gap like for like rather than a mix effect. The "All" row
    is the company-wide average, which is exactly what can hide a gap.

    Groups smaller than var('min_group_size') are suppressed.
*/

with active as (
    select job_level, gender, compa_ratio, base_salary, band_mid
    from {{ ref('dim_employee') }}
    where is_active
),

payroll as (
    select sum(base_salary) as total_base_payroll from active
),

by_level as (
    select job_level, gender, count(*) as n,
           avg(compa_ratio) as avg_compa_ratio, avg(base_salary) as avg_base_salary
    from active
    group by 1, 2
),

all_levels as (
    select 'All' as job_level, gender, count(*) as n,
           avg(compa_ratio) as avg_compa_ratio, avg(base_salary) as avg_base_salary
    from active
    group by 2
),

groups as (
    select * from by_level
    union all
    select * from all_levels
),

men as (
    select job_level, n as men_n, avg_compa_ratio as men_compa_ratio
    from groups
    where gender = 'Man'
),

-- cost to lift each person below the men's average compa-ratio at their level up to it
cost as (
    select a.job_level, a.gender,
           sum(greatest(0, m.men_compa_ratio - a.compa_ratio) * a.band_mid) as cost_to_close
    from active a
    join men m on a.job_level = m.job_level
    where a.gender <> 'Man'
    group by 1, 2
)

select
    g.job_level,
    g.gender,
    g.n < {{ var('min_group_size') }}                       as is_suppressed,
    {{ suppress('g.n', 'g.n') }}                            as employees,
    {{ suppress('g.n', 'round(g.avg_compa_ratio, 3)') }}    as avg_compa_ratio,
    {{ suppress('g.n', 'round(g.avg_base_salary, -2)') }}   as avg_base_salary,
    case
        when g.gender <> 'Man'
         and g.n >= {{ var('min_group_size') }}
         and m.men_n >= {{ var('min_group_size') }}
        then round((g.avg_compa_ratio / m.men_compa_ratio - 1) * 100, 1)
    end                                                     as gap_vs_men_pct,
    case
        when g.job_level <> 'All'
         and g.n >= {{ var('min_group_size') }}
         and m.men_n >= {{ var('min_group_size') }}
        then round(c.cost_to_close, -3)
    end                                                     as cost_to_close_usd,
    case
        when g.job_level <> 'All'
         and g.n >= {{ var('min_group_size') }}
         and m.men_n >= {{ var('min_group_size') }}
        then round(c.cost_to_close / p.total_base_payroll * 100, 2)
    end                                                     as cost_to_close_pct_of_payroll
from groups g
cross join payroll p
left join men m on g.job_level = m.job_level
left join cost c on g.job_level = c.job_level and g.gender = c.gender
