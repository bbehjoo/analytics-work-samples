{{
  config(schema='people_metrics', access='public')
}}

/*
    bridge_employee_sales_rep
    -------------------------
    Keys only: which employee is which sales rep. This is how the revenue domain
    joins to people without ever touching an HR record. It carries no name, pay
    or anything else about the person.
*/

select
    {{ dbt_utils.generate_surrogate_key(['worker_id']) }}            as employee_key,
    {{ dbt_utils.generate_surrogate_key(['salesforce_user_id']) }}   as sales_rep_key
from {{ ref('stg_hris__workers') }}
where salesforce_user_id is not null
