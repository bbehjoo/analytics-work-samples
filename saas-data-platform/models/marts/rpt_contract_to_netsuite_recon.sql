/*
    rpt_contract_to_netsuite_recon  —  Salesforce <-> NetSuite reconciliation
    -------------------------------------------------------------------------
    Grain: one row per contract <-> sales order pair, plus each side's unmatched
    rows. A finance-hygiene report that surfaces where the CRM and the ERP
    disagree, with a status and a discrepancy category so an analyst can pivot
    "$ at risk by category" and drill to the underlying IDs.
*/

with recon as (
    select * from {{ ref('int_recon__contract_order_match') }}
)

select
    {{ dbt_utils.generate_surrogate_key(["coalesce(contract_id, '')", "coalesce(sales_order_id, '')"]) }} as recon_key,
    {{ dbt_utils.generate_surrogate_key(['account_id']) }} as account_key,

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

    match_status,
    discrepancy_category
from recon
