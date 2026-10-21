-- Proof test: every quoted opportunity has exactly one primary quote, and that
-- quote's net total equals what was booked, to the cent. Churn is not quoted.
-- Returns any opportunity that breaks the chain (expected: 0 rows).
with opportunities as (
    select opportunity_id
    from {{ ref('stg_salesforce__opportunities') }}
    where opportunity_type <> 'Churn'
),

booked as (
    select opportunity_id, sum(line_amount) as booked_amount
    from {{ ref('stg_salesforce__opportunity_line_items') }}
    group by 1
),

primary_quotes as (
    select opportunity_id, count(*) as primary_quotes, sum(net_total) as quote_amount
    from {{ ref('fct_quote') }}
    where is_primary
    group by 1
)

select
    o.opportunity_id,
    coalesce(p.primary_quotes, 0)   as primary_quotes,
    b.booked_amount,
    p.quote_amount
from opportunities o
left join booked b on o.opportunity_id = b.opportunity_id
left join primary_quotes p on o.opportunity_id = p.opportunity_id
where coalesce(p.primary_quotes, 0) <> 1
   or abs(coalesce(p.quote_amount, 0) - coalesce(b.booked_amount, 0)) >= 0.01
