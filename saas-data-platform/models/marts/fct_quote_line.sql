/*
    fct_quote_line
    --------------
    Pricing fact at quote-line grain: list price, discount and net price for
    every product on every quote version. Filter is_primary for what deals were
    actually booked on; keep the drafts to see how a price moved during a deal.
*/

with lines as (
    select * from {{ ref('int_quote_lines__pricing') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['quote_line_id']) }}  as quote_line_key,
    {{ dbt_utils.generate_surrogate_key(['account_id']) }}     as account_key,
    {{ dbt_utils.generate_surrogate_key(['product_id']) }}     as product_key,
    {{ dbt_utils.generate_surrogate_key(['owner_id']) }}       as sales_rep_key,
    quote_line_id,
    quote_id,
    opportunity_id,
    account_id,
    product_id,
    owner_id,
    is_primary,
    quote_status,
    quote_date,
    close_date,
    opportunity_type,
    price_book_region,
    quantity,
    is_recurring,
    list_unit_price,
    net_unit_price,
    discount_pct,
    list_amount,
    discount_amount,
    net_amount
from lines
