-- Price books: one per region.
-- depends_on: {{ ref('salesforce_price_books') }}
with source as (
    select * from {{ source('salesforce', 'price_books') }}
)

select
    price_book_id,
    price_book_name,
    cast(region as varchar)     as region,
    currency_code,
    is_active = 1               as is_active
from source
