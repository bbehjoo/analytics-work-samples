-- Opportunity line items: product-level lines; the grain of bookings / ACV.
-- `line_amount` is the booking's annualized contribution for recurring products
-- (a full annual amount for new business, the incremental annual amount for an
-- expansion, a negative annual amount for a downgrade) and the fee for one-time
-- products. ACV/TCV are derived from this in int_opportunity_lines__acv.
-- depends_on: {{ ref('salesforce_opportunity_line_items') }}
with source as (
    select * from {{ source('salesforce', 'opportunity_line_items') }}
)

select
    opportunity_line_id,
    opportunity_id,
    product_id,
    cast(quantity as integer)       as quantity,
    cast(unit_price as double)      as unit_price,
    cast(term_months as integer)    as term_months,
    is_recurring = 1                as is_recurring,
    cast(line_amount as double)     as line_amount
from source
