/*
    fct_quote
    ---------
    Quote grain: the price of each quote version against list, and whether a
    discount above policy was approved.

    Discount policy (var('discount_approval_threshold'), var('cfo_approval_threshold')):
    new pricing (New Business or Expansion) more than 25% off list needs a Sales
    VP's approval, and more than 35% the CFO's. Renewals and downgrades keep the
    contracted price, so they need none. The discount is measured over the
    positive lines (what's being sold), against list.
*/

{% set threshold = var('discount_approval_threshold') %}
{% set cfo = var('cfo_approval_threshold') %}

with lines as (
    select * from {{ ref('int_quote_lines__pricing') }}
),

quotes as (
    select * from {{ ref('stg_salesforce__quotes') }}
),

opportunities as (
    select opportunity_id, opportunity_type, close_date, is_closed, is_won
    from {{ ref('stg_salesforce__opportunities') }}
),

approvals as (
    select
        quote_id,
        max(approval_level)                                                as approval_level,
        max(case when approval_status = 'Approved' then 1 else 0 end) = 1  as is_approved,
        min(requested_date)                                                as requested_date,
        max(decided_date)                                                  as decided_date
    from {{ ref('stg_salesforce__quote_approvals') }}
    group by 1
),

totals as (
    select
        quote_id,
        count(*)                                                             as line_count,
        sum(case when quantity > 0 then list_amount else 0 end)              as list_amount,
        sum(case when quantity > 0 then net_amount else 0 end)               as sold_net_amount,
        sum(net_amount)                                                      as net_total
    from lines
    group by 1
),

priced as (
    select
        q.*,
        o.opportunity_type,
        o.close_date,
        o.is_won,
        t.line_count,
        t.list_amount,
        t.sold_net_amount,
        t.net_total,
        case when t.list_amount > 0 then 1 - t.sold_net_amount / t.list_amount end as discount_pct
    from quotes q
    inner join totals t on q.quote_id = t.quote_id
    left join opportunities o on q.opportunity_id = o.opportunity_id
)

select
    {{ dbt_utils.generate_surrogate_key(['p.quote_id']) }}     as quote_key,
    {{ dbt_utils.generate_surrogate_key(['p.account_id']) }}   as account_key,
    {{ dbt_utils.generate_surrogate_key(['p.owner_id']) }}     as sales_rep_key,
    p.quote_id,
    p.opportunity_id,
    p.account_id,
    p.owner_id,
    p.is_primary,
    p.quote_status,
    p.quote_date,
    p.close_date,
    p.opportunity_type,
    cast(extract(month from p.close_date) as integer) in (3, 6, 9, 12)   as is_quarter_end_month,
    p.line_count,
    p.list_amount,
    p.list_amount - p.sold_net_amount                                     as discount_amount,
    p.sold_net_amount                                                     as net_amount,
    p.net_total,
    round(p.discount_pct, 4)                                              as discount_pct,
    (p.is_primary and p.quote_status = 'Accepted'
        and p.opportunity_type in ('New Business', 'Expansion')
        and p.discount_pct > {{ threshold }})                             as requires_approval,
    case
        when p.is_primary and p.quote_status = 'Accepted'
         and p.opportunity_type in ('New Business', 'Expansion')
         and p.discount_pct > {{ cfo }} then 'CFO'
        when p.is_primary and p.quote_status = 'Accepted'
         and p.opportunity_type in ('New Business', 'Expansion')
         and p.discount_pct > {{ threshold }} then 'Sales VP'
    end                                                                   as approval_level_required,
    coalesce(a.is_approved, false)                                        as is_approved,
    a.approval_level,
    {{ dbt.datediff('a.requested_date', 'a.decided_date', 'day') }}      as approval_cycle_days
from priced p
left join approvals a on p.quote_id = a.quote_id
