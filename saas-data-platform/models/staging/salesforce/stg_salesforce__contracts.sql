-- Contracts: signed deals. `external_order_ref` reconciles to NetSuite orders.
-- depends_on: {{ ref('salesforce_contracts') }}
with source as (
    select * from {{ source('salesforce', 'contracts') }}
)

select
    contract_id,
    account_id,
    contract_number,
    cast(start_date as date)              as contract_start_date,
    cast(end_date as date)                as contract_end_date,
    cast(term_months as integer)          as term_months,
    contract_status,
    currency_code,
    external_order_ref,
    cast(total_contract_value as double)  as total_contract_value
from source
