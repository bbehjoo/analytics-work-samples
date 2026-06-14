-- Accounts: one row per customer/prospect, with firmographics and segmentation.
-- depends_on: {{ ref('salesforce_accounts') }}  -- forces seed -> staging order under `dbt build`
with source as (
    select * from {{ source('salesforce', 'accounts') }}
)

select
    account_id,
    account_name,
    industry,
    billing_country,
    geo_region,
    division,
    segment,
    account_tier,
    account_currency,
    owner_id,
    cast(created_date as date)      as account_created_date,
    is_customer = 1                 as is_customer
from source
