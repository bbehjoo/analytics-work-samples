/*
    recon_summary
    -------------
    Executive one-liner for the Salesforce <-> NetSuite reconciliation:
    "$ at risk by discrepancy category". Drives the finance-hygiene section of the
    insights report and a Slack/exec summary. Drill from here into
    rpt_contract_to_netsuite_recon for the underlying contract/order IDs.
*/
select
    discrepancy_category,
    match_status,
    count(*) as record_count,
    round(sum(abs(coalesce(amount_variance, sfdc_contract_amount, ns_order_amount))), 0)
        as dollars_at_risk
from {{ ref('rpt_contract_to_netsuite_recon') }}
group by 1, 2
order by dollars_at_risk desc
