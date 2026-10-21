{{
  config(materialized='view')
}}

/*
    int_contract_lines__normalized
    ------------------------------
    Grain: one row per subscription segment (a constant-ARR period for an
    account x product). Enriches the ARR source-of-truth (subscriptions) with
    product hierarchy attributes. Shared feeder for the ARR measurement spine
    and for usage entitlement.
*/

with subscriptions as (
    select * from {{ ref('stg_salesforce__subscriptions') }}
    where is_recurring
),

products as (
    select * from {{ ref('stg_salesforce__products') }}
)

select
    s.subscription_id,
    s.contract_id,
    s.account_id,
    s.product_id,
    p.product_name,
    p.line_of_business,
    p.product_family,
    s.quantity                      as entitled_units,
    s.annual_recurring_amount,
    s.subscription_start_date,
    s.subscription_end_date,
    s.subscription_status
from subscriptions s
left join products p on s.product_id = p.product_id
