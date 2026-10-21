-- Price book entries: the list price of each product, per price book, per year.
-- depends_on: {{ ref('salesforce_price_book_entries') }}
with source as (
    select * from {{ source('salesforce', 'price_book_entries') }}
)

select
    price_book_entry_id,
    price_book_id,
    product_id,
    cast(effective_year as integer)     as effective_year,
    cast(list_unit_price as double)     as list_unit_price
from source
