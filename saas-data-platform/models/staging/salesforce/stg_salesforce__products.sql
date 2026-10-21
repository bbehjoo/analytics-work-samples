-- Products: catalog with LOB / family hierarchy and recurring vs one-time flag.
-- depends_on: {{ ref('salesforce_products') }}
with source as (
    select * from {{ source('salesforce', 'products') }}
)

select
    product_id,
    product_name,
    product_sku,
    line_of_business,
    product_family,
    product_category,
    is_recurring = 1                as is_recurring,
    is_active = 1                   as is_active,
    cast(list_unit_price as double) as list_unit_price
from source
