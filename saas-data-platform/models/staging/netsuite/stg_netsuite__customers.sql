-- NetSuite customers; bridges to Salesforce accounts via sfdc_account_external_id.
-- depends_on: {{ ref('netsuite_customers') }}
with source as (
    select * from {{ source('netsuite', 'customers') }}
)

select
    ns_customer_id,
    customer_name,
    sfdc_account_external_id,
    subsidiary,
    currency_code
from source
