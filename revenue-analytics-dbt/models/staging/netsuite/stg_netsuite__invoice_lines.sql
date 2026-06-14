-- NetSuite invoice lines by item.
-- depends_on: {{ ref('netsuite_invoice_lines') }}
with source as (
    select * from {{ source('netsuite', 'invoice_lines') }}
)

select
    invoice_line_id,
    invoice_id,
    ns_item_id,
    cast(quantity as integer)       as quantity,
    cast(rate as double)            as rate,
    cast(line_amount as double)     as line_amount
from source
