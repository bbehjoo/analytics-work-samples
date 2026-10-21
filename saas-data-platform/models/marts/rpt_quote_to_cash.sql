/*
    rpt_quote_to_cash
    -----------------
    Grain: one row per won opportunity. The whole chain in one place:
    primary quote -> booking -> contract -> NetSuite order -> invoice, with one
    status that says where (if anywhere) the chain breaks.

    The quote is checked against the booking to the cent; the contract against
    the order uses the existing CRM-to-ERP reconciliation. Discounts above policy
    without an approval are flagged too, because a deal priced outside policy is
    a control failure even if every system agrees on the amount.
*/

with won as (
    select opportunity_id, account_id, opportunity_type, close_date, contract_id
    from {{ ref('stg_salesforce__opportunities') }}
    where is_won
),

booked as (
    select opportunity_id, sum(line_amount) as booked_amount
    from {{ ref('stg_salesforce__opportunity_line_items') }}
    group by 1
),

primary_quote as (
    select opportunity_id, quote_id, net_total, discount_pct, requires_approval, is_approved
    from {{ ref('fct_quote') }}
    where is_primary
),

recon as (
    select contract_id, sales_order_id, ns_order_amount, ns_invoice_amount, discrepancy_category
    from {{ ref('rpt_contract_to_netsuite_recon') }}
    where contract_id is not null
)

select
    {{ dbt_utils.generate_surrogate_key(['w.opportunity_id']) }}   as quote_to_cash_key,
    {{ dbt_utils.generate_surrogate_key(['w.account_id']) }}       as account_key,
    w.opportunity_id,
    w.account_id,
    w.opportunity_type,
    w.close_date,
    pq.quote_id                                                    as primary_quote_id,
    pq.discount_pct,
    pq.net_total                                                   as quote_amount,
    b.booked_amount,
    abs(coalesce(pq.net_total, 0) - coalesce(b.booked_amount, 0)) < 0.01   as quote_ties_to_booking,
    coalesce(pq.requires_approval and not pq.is_approved, false)  as is_unapproved_discount,
    w.contract_id,
    r.sales_order_id,
    r.ns_order_amount,
    r.ns_invoice_amount,
    r.discrepancy_category                                         as contract_to_order_status,
    case
        when pq.quote_id is null                                   then 'no primary quote'
        when abs(pq.net_total - b.booked_amount) >= 0.01           then 'quote does not tie to booking'
        when pq.requires_approval and not pq.is_approved           then 'discount not approved'
        when r.discrepancy_category is null                        then 'no contract'
        when r.discrepancy_category <> 'matched_clean'             then r.discrepancy_category
        else 'clean'
    end                                                            as quote_to_cash_status
from won w
left join booked b on w.opportunity_id = b.opportunity_id
left join primary_quote pq on w.opportunity_id = pq.opportunity_id
left join recon r on w.contract_id = r.contract_id
