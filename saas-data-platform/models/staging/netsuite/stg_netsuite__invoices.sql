-- NetSuite invoices; linked to a sales order, drives billed-vs-ordered coverage.
-- depends_on: {{ ref('netsuite_invoices') }}
with source as (
    select * from {{ source('netsuite', 'invoices') }}
)

select
    invoice_id,
    ns_customer_id,
    sales_order_id,
    invoice_number,
    cast(invoice_date as date)      as invoice_date,
    cast(invoice_total as double)   as invoice_total,
    invoice_status,
    currency_code
from source
