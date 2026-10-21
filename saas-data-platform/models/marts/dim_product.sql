/*
    dim_product
    -----------
    Conformed product dimension with the line-of-business / family hierarchy,
    recurring-vs-one-time classification, and the NetSuite item bridge.
*/

with products as (
    select * from {{ ref('stg_salesforce__products') }}
),

ns_items as (
    select * from {{ ref('stg_netsuite__items') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['p.product_id']) }} as product_key,
    p.product_id,
    p.product_name,
    p.product_sku,
    p.line_of_business,
    p.product_family,
    p.product_category,
    p.is_recurring,
    p.is_active,
    p.list_unit_price,
    nsi.ns_item_id
from products p
left join ns_items nsi on p.product_id = nsi.sfdc_product_external_id
