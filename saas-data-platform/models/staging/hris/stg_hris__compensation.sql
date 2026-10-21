-- Compensation: current pay per worker, in USD.
-- depends_on: {{ ref('hris_compensation') }}
with source as (
    select * from {{ source('hris', 'compensation') }}
)

select
    cast(worker_id as varchar)          as worker_id,
    cast(effective_date as date)        as effective_date,
    cast(base_salary_usd as integer)    as base_salary,
    cast(bonus_target_pct as double)    as bonus_target_pct,
    cast(equity_grant_usd as integer)   as equity_grant_usd
from source
