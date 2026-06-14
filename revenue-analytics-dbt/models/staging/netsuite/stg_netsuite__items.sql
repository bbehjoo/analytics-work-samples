-- NetSuite items; bridges to Salesforce products via sfdc_product_external_id.
-- depends_on: {{ ref('netsuite_items') }}
with source as (
    select * from {{ source('netsuite', 'items') }}
)

select
    ns_item_id,
    item_name,
    item_type,
    sfdc_product_external_id
from source
