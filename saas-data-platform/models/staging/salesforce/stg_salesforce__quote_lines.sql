-- Quote lines (Salesforce CPQ): list price, discount and net price per product.
-- depends_on: {{ ref('salesforce_quote_lines') }}
with source as (
    select * from {{ source('salesforce', 'quote_lines') }}
)

select
    quote_line_id,
    quote_id,
    product_id,
    cast(quantity as integer)           as quantity,
    cast(list_unit_price as double)     as list_unit_price,
    cast(discount_pct as double)        as discount_pct,
    cast(net_unit_price as double)      as net_unit_price,
    cast(net_total as double)           as net_total,
    is_recurring = 1                    as is_recurring,
    cast(term_months as integer)        as term_months
from source
