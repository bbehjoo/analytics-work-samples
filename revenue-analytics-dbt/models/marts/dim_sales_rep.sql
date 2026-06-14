/*
    dim_sales_rep
    -------------
    Sales rep dimension (Salesforce users who own accounts and opportunities),
    with their sales team and region for territory-level analysis.
*/

with users as (
    select * from {{ ref('stg_salesforce__users') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['user_id']) }} as sales_rep_key,
    user_id,
    user_name           as sales_rep_name,
    sales_team,
    sales_region,
    role
from users
