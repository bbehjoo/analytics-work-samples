-- Subscriptions: recurring lines with effective date ranges and an annual
-- recurring amount. Each row is a constant-ARR segment for an account x product;
-- amount changes (upsell/downgrade) and gaps (churn) are represented as separate
-- segments. This is the ARR source of truth.
-- depends_on: {{ ref('salesforce_subscriptions') }}
with source as (
    select * from {{ source('salesforce', 'subscriptions') }}
)

select
    subscription_id,
    contract_id,
    account_id,
    product_id,
    cast(quantity as integer)                 as quantity,
    cast(annual_recurring_amount as double)   as annual_recurring_amount,
    cast(unit_price as double)                as unit_price,
    billing_frequency,
    cast(subscription_start_date as date)     as subscription_start_date,
    cast(subscription_end_date as date)       as subscription_end_date,
    is_recurring = 1                          as is_recurring,
    status                                    as subscription_status
from source
