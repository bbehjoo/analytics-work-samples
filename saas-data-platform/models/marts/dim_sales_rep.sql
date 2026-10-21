/*
    dim_sales_rep
    -------------
    Sales rep dimension (Salesforce users who own accounts and opportunities),
    with their sales team and region for territory-level analysis.

    employee_key comes from the people domain's key-only bridge, so revenue
    analysis can join to people metrics without ever reading an HR record.
*/

with users as (
    select * from {{ ref('stg_salesforce__users') }}
),

bridge as (
    select * from {{ ref('bridge_employee_sales_rep') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['u.user_id']) }} as sales_rep_key,
    u.user_id,
    u.user_name           as sales_rep_name,
    u.sales_team,
    u.sales_region,
    u.role,
    b.employee_key
from users u
left join bridge b
  on b.sales_rep_key = {{ dbt_utils.generate_surrogate_key(['u.user_id']) }}
