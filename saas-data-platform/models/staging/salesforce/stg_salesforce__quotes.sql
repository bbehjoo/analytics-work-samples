-- Quotes (Salesforce CPQ): every version a rep sent. One per opportunity is primary,
-- and the primary quote is what the deal was booked on.
-- depends_on: {{ ref('salesforce_quotes') }}
with source as (
    select * from {{ source('salesforce', 'quotes') }}
)

select
    quote_id,
    opportunity_id,
    account_id,
    owner_id,
    price_book_id,
    quote_status,
    is_primary = 1                      as is_primary,
    cast(created_date as date)          as quote_date,
    cast(expiration_date as date)       as expiration_date,
    cast(contact_name as varchar)       as contact_name,
    cast(contact_email as varchar)      as contact_email
from source
