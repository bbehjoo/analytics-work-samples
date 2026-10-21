/*
    dim_account
    -----------
    Conformed customer dimension. One row per Salesforce account, enriched with
    the owning rep, the NetSuite customer bridge, and two convenience measures
    (first contract date and current ARR) for quick filtering and segmentation.
*/

with accounts as (
    select * from {{ ref('stg_salesforce__accounts') }}
),

users as (
    select * from {{ ref('stg_salesforce__users') }}
),

ns_customers as (
    select * from {{ ref('stg_netsuite__customers') }}
),

first_contract as (
    select account_id, min(contract_start_date) as first_contract_date
    from {{ ref('stg_salesforce__contracts') }}
    group by 1
),

current_arr as (
    select account_id, sum(arr) as current_arr
    from {{ ref('int_arr__account_product_month') }}
    where measurement_month = (
        select max(measurement_month) from {{ ref('int_arr__account_product_month') }}
    )
    group by 1
)

select
    {{ dbt_utils.generate_surrogate_key(['a.account_id']) }} as account_key,
    a.account_id,
    a.account_name,
    a.industry,
    a.billing_country,
    a.geo_region,
    a.division,
    a.segment,
    a.account_tier,
    a.account_currency,
    a.owner_id,
    u.user_name                     as account_owner,
    u.sales_region,
    u.sales_team,
    nsc.ns_customer_id,
    a.is_customer,
    fc.first_contract_date,
    coalesce(ca.current_arr, 0)     as current_arr
from accounts a
left join users u on a.owner_id = u.user_id
left join ns_customers nsc on a.account_id = nsc.sfdc_account_external_id
left join first_contract fc on a.account_id = fc.account_id
left join current_arr ca on a.account_id = ca.account_id
