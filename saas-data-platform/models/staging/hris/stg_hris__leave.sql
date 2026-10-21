-- Leaves of absence. leave_type (Medical / Parental / Personal) is health information.
-- depends_on: {{ ref('hris_leave') }}
with source as (
    select * from {{ source('hris', 'leave') }}
)

select
    cast(leave_id as varchar)     as leave_id,
    cast(worker_id as varchar)    as worker_id,
    cast(leave_type as varchar)   as leave_type,
    cast(start_date as date)      as start_date,
    cast(end_date as date)        as end_date
from source
