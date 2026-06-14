-- Users: the sales reps who own accounts and opportunities.
-- depends_on: {{ ref('salesforce_users') }}
with source as (
    select * from {{ source('salesforce', 'users') }}
)

select
    user_id,
    user_name,
    sales_team,
    sales_region,
    role
from source
