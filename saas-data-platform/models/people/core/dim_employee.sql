/*
    dim_employee
    ------------
    One row per person ever employed, as of the HR snapshot date: identity, org
    placement, pay against band, current leave and gender. The most sensitive
    table in the warehouse.

    Private to People Analytics (access: private) with an enforced contract.
    Nobody queries it directly: each role reads its own secure_<role> view, built
    from the column tags in _people_core__models.yml by the secure_view() macro.
*/

with workers as (
    select * from {{ ref('stg_hris__workers') }}
),

comp as (
    select * from {{ ref('stg_hris__compensation') }}
),

bands as (
    select * from {{ ref('stg_hris__comp_bands') }}
),

leave_on_as_of as (
    select worker_id, max(leave_type) as leave_type
    from {{ ref('stg_hris__leave') }}
    where cast('{{ var("people_as_of") }}' as date) between start_date and end_date
    group by 1
)

select
    {{ dbt_utils.generate_surrogate_key(['w.worker_id']) }}   as employee_key,
    w.worker_id,
    w.employee_name,
    w.work_email,
    w.personal_email,
    w.home_postal_code,
    w.date_of_birth,
    w.department,
    w.job_title,
    w.region,
    w.country,
    w.manager_id,
    w.job_level,
    w.hire_date,
    w.termination_date,
    w.termination_type,
    w.termination_date is null                              as is_active,
    c.base_salary,
    c.bonus_target_pct,
    c.equity_grant_usd,
    b.band_mid,
    cast(round(c.base_salary * 1.0 / b.band_mid, 3) as double) as compa_ratio,
    w.gender,
    l.leave_type                                            as current_leave_type,
    w.salesforce_user_id is not null                        as is_sales_rep,
    w.salesforce_user_id
from workers w
left join comp c on w.worker_id = c.worker_id
left join bands b on w.job_level = b.job_level and w.region = b.region
left join leave_on_as_of l on w.worker_id = l.worker_id
