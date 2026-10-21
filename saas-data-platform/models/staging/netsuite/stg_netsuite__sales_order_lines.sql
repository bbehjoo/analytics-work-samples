-- NetSuite sales order lines by item.
-- depends_on: {{ ref('netsuite_sales_order_lines') }}
with source as (
    select * from {{ source('netsuite', 'sales_order_lines') }}
)

select
    sales_order_line_id,
    sales_order_id,
    ns_item_id,
    cast(quantity as integer)       as quantity,
    cast(rate as double)            as rate,
    cast(line_amount as double)     as line_amount
from source
