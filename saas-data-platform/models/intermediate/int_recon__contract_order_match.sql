{{
  config(materialized='view')
}}

/*
    int_recon__contract_order_match
    -------------------------------
    Grain: one row per contract <-> sales order pair, plus the unmatched rows from
    each side (a FULL OUTER JOIN on external_order_ref).

    Compares the Salesforce contract amount to the NetSuite order amount and the
    billed (invoiced) amount, then assigns a match status and a discrepancy
    category. Because the seeded discrepancies are mutually exclusive per contract,
    the category precedence below resolves each row to exactly one bucket.
*/

with contracts as (
    select * from {{ ref('stg_salesforce__contracts') }}
),

orders as (
    select * from {{ ref('stg_netsuite__sales_orders') }}
),

customers as (
    select * from {{ ref('stg_netsuite__customers') }}
),

invoices as (
    select
        sales_order_id,
        sum(invoice_total) as ns_invoice_amount,
        count(*)           as invoice_count
    from {{ ref('stg_netsuite__invoices') }}
    group by 1
),

joined as (
    select
        c.contract_id,
        c.contract_number,
        c.account_id                    as sfdc_account_id,
        c.total_contract_value          as sfdc_contract_amount,
        c.contract_start_date,
        c.currency_code                 as sfdc_currency,
        o.sales_order_id,
        o.order_number,
        o.order_total                   as ns_order_amount,
        o.order_date,
        o.currency_code                 as ns_currency,
        cust.sfdc_account_external_id   as order_account_id,
        inv.ns_invoice_amount,
        inv.invoice_count,
        coalesce(c.external_order_ref, o.external_order_ref) as external_order_ref
    from contracts c
    full outer join orders o
        on c.external_order_ref = o.external_order_ref
    left join customers cust on o.ns_customer_id = cust.ns_customer_id
    left join invoices inv on o.sales_order_id = inv.sales_order_id
),

computed as (
    select
        *,
        coalesce(sfdc_account_id, order_account_id)                 as account_id,
        sfdc_contract_amount - ns_order_amount                      as amount_variance,
        (sfdc_contract_amount - ns_order_amount)
            / nullif(sfdc_contract_amount, 0)                       as amount_variance_pct,
        {{ dbt.datediff('contract_start_date', 'order_date', 'day') }} as date_variance_days,
        (sfdc_currency <> ns_currency)                              as currency_variance,
        ns_invoice_amount / nullif(ns_order_amount, 0)              as invoice_coverage_pct
    from joined
)

select
    account_id,
    contract_id,
    contract_number,
    external_order_ref,
    sales_order_id,
    order_number,
    contract_start_date,
    order_date,
    sfdc_contract_amount,
    ns_order_amount,
    ns_invoice_amount,
    amount_variance,
    amount_variance_pct,
    date_variance_days,
    currency_variance,
    invoice_coverage_pct,
    case
        when contract_id is null then 'unmatched_netsuite'
        when sales_order_id is null then 'unmatched_sfdc'
        when abs(amount_variance) > 50 and abs(amount_variance_pct) > 0.01 then 'variance'
        else 'matched'
    end as match_status,
    case
        when contract_id is null then 'orphan_in_netsuite'
        when sales_order_id is null then 'missing_in_netsuite'
        when abs(amount_variance) > 50 and abs(amount_variance_pct) > 0.01 then 'amount_mismatch'
        when abs(amount_variance) > 0 and abs(amount_variance) <= 50 then 'currency_rounding'
        when coalesce(invoice_coverage_pct, 0) < 0.999 then 'partially_invoiced'
        when abs(date_variance_days) > 7 then 'timing_difference'
        else 'matched_clean'
    end as discrepancy_category
from computed
