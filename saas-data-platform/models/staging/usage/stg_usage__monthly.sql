-- Monthly product usage / metering: consumed units and value per account x product.
-- depends_on: {{ ref('usage_monthly') }}
with source as (
    select * from {{ source('usage', 'usage_monthly') }}
)

select
    account_id,
    product_id,
    cast(usage_month as date)       as usage_month,
    cast(consumed_units as double)  as consumed_units,
    cast(consumed_value as double)  as consumed_value
from source
