-- Opportunities: open pipeline and closed (won/lost) deals.
-- depends_on: {{ ref('salesforce_opportunities') }}
with source as (
    select * from {{ source('salesforce', 'opportunities') }}
)

select
    opportunity_id,
    account_id,
    owner_id,
    opportunity_name,
    opportunity_type,
    stage_name,
    forecast_category,
    cast(amount as double)          as opportunity_amount,
    currency_code,
    cast(term_months as integer)    as term_months,
    cast(created_date as date)      as created_date,
    cast(close_date as date)        as close_date,
    is_closed = 1                   as is_closed,
    is_won = 1                      as is_won,
    nullif(contract_id, '')         as contract_id
from source
