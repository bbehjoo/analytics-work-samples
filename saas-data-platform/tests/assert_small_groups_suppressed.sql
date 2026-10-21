{{ config(group='people') }}  {# owned by People Analytics, so it may read the private dim_employee #}
-- Proof test: no people metric is ever shown for a group smaller than
-- var('min_group_size'), and no group at or above it is hidden by mistake.
-- Group sizes are recounted from dim_employee, independently of the reports.
-- Returns one row per breach (expected: 0).
{% set k = var('min_group_size') %}

with dept_n as (
    select department, count(*) as n
    from {{ ref('dim_employee') }}
    where is_active
    group by 1
),

level_gender_n as (
    select job_level, gender, count(*) as n
    from {{ ref('dim_employee') }}
    where is_active
    group by 1, 2
),

men_n as (
    select job_level, n from level_gender_n where gender = 'Man'
)

select 'department_summary' as report, s.department as grp, d.n, 'small group shown' as problem
from {{ ref('rpt_people__department_summary') }} s
join dept_n d on s.department = d.department
where d.n < {{ k }}
  and (not s.is_suppressed
       or s.headcount is not null or s.attrition_rate_ttm is not null
       or s.voluntary_attrition_rate_ttm is not null or s.avg_compa_ratio is not null
       or s.avg_base_pay_band is not null)

union all

select 'department_summary', s.department, d.n, 'large group hidden'
from {{ ref('rpt_people__department_summary') }} s
join dept_n d on s.department = d.department
where d.n >= {{ k }} and s.is_suppressed

union all

select 'pay_equity', p.job_level || ' ' || p.gender, g.n, 'small group shown'
from {{ ref('rpt_people__pay_equity') }} p
join level_gender_n g on p.job_level = g.job_level and p.gender = g.gender
where g.n < {{ k }}
  and (not p.is_suppressed or p.employees is not null
       or p.avg_compa_ratio is not null or p.gap_vs_men_pct is not null)

union all

select 'pay_equity', p.job_level || ' ' || p.gender, m.n, 'gap measured against fewer than k men'
from {{ ref('rpt_people__pay_equity') }} p
join men_n m on p.job_level = m.job_level
where m.n < {{ k }} and p.gap_vs_men_pct is not null

union all

select 'ai_department_summary', s.department, d.n, 'small group shown to the AI agent'
from {{ ref('secure_ai_agent__department_summary') }} s
join dept_n d on s.department = d.department
where d.n < {{ k }} and (not s.is_suppressed or s.headcount is not null)
