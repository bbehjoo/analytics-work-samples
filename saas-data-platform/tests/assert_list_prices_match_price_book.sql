-- Proof test: no quote invents its own list price. Every quote line's list price
-- equals the price book entry for its region, product and year.
-- Returns any line that doesn't (expected: 0 rows).
select
    quote_line_id,
    quote_id,
    product_id,
    price_book_region,
    list_unit_price,
    price_book_list_price
from {{ ref('int_quote_lines__pricing') }}
where price_book_list_price is null
   or abs(list_unit_price - price_book_list_price) > 0.005
