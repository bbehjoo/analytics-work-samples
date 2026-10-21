-- Discount approvals (Salesforce CPQ advanced approvals): who signed off on a
-- discount above policy, and how long it took.
-- depends_on: {{ ref('salesforce_quote_approvals') }}
with source as (
    select * from {{ source('salesforce', 'quote_approvals') }}
)

select
    approval_id,
    quote_id,
    approval_level,
    cast(approver_name as varchar)      as approver_name,
    approval_status,
    cast(requested_date as date)        as requested_date,
    cast(decided_date as date)          as decided_date
from source
