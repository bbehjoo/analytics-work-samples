-- Workers: one row per person ever employed. Identity, org placement, dates.
-- depends_on: {{ ref('hris_workers') }}
with source as (
    select * from {{ source('hris', 'workers') }}
)

select
    cast(worker_id as varchar)           as worker_id,
    cast(full_name as varchar)           as employee_name,
    cast(work_email as varchar)          as work_email,
    cast(personal_email as varchar)      as personal_email,
    cast(home_postal_code as varchar)    as home_postal_code,
    cast(date_of_birth as date)          as date_of_birth,
    cast(gender as varchar)              as gender,
    cast(department as varchar)          as department,
    cast(job_title as varchar)           as job_title,
    cast(job_level as varchar)           as job_level,
    cast(region as varchar)              as region,
    cast(country as varchar)             as country,
    cast(manager_id as varchar)          as manager_id,
    cast(hire_date as date)              as hire_date,
    cast(termination_date as date)       as termination_date,
    cast(termination_type as varchar)    as termination_type,
    cast(salesforce_user_id as varchar)  as salesforce_user_id
from source
