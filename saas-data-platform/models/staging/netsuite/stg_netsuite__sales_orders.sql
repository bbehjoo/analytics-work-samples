-- NetSuite sales orders; `external_order_ref` reconciles to a Salesforce contract.
-- depends_on: {{ ref('netsuite_sales_orders') }}
with source as (
    select * from {{ source('netsuite', 'sales_orders') }}
)

select
    sales_order_id,
    ns_customer_id,
    order_number,
    external_order_ref,
    cast(order_date as date)        as order_date,
    order_status,
    cast(order_total as double)     as order_total,
    currency_code
from source
