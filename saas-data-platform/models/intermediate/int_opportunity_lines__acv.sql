{{
  config(materialized='view')
}}

/*
    int_opportunity_lines__acv
    --------------------------
    Grain: one row per opportunity line item (open pipeline + closed deals).

    Computes the two headline sales measures and classifies each line into a
    revenue category. This is the feeder for fct_acv.

    ACV vs TCV (per the business definition used here):
      * ACV = average annual recurring value + frontloaded (full) one-time fees.
              For a recurring line, `line_amount` already represents the annual
              recurring amount, so ACV = line_amount. One-time fees are added in
              full (not amortized).
      * TCV = total contract value = recurring annual amount x term-years
              (+ one-time fees in full).
      Worked example: a 3-year line at $100k/yr recurring -> ACV $100k, TCV $300k;
      a $10k one-time line -> ACV $10k, TCV $10k. Deal totals: ACV $110k, TCV $310k.

    Revenue category (new_logo / cross_sell / upsell / downgrade / scheduled /
    churn) is derived from the opportunity type plus the account's deal history
    (is this the account's first landing? is this product new to the account?).
*/

with opp_lines as (
    select * from {{ ref('stg_salesforce__opportunity_line_items') }}
),

opportunities as (
    select * from {{ ref('stg_salesforce__opportunities') }}
),

products as (
    select * from {{ ref('stg_salesforce__products') }}
),

users as (
    select * from {{ ref('stg_salesforce__users') }}
),

joined as (
    select
        ol.opportunity_line_id,
        ol.opportunity_id,
        o.account_id,
        o.owner_id,
        u.user_name              as opportunity_owner,
        u.sales_region,
        u.sales_team,
        ol.product_id,
        p.product_name,
        p.line_of_business,
        p.product_family,
        o.opportunity_type,
        o.stage_name,
        o.forecast_category,
        o.is_closed,
        o.is_won,
        o.close_date,
        cast(extract(year from o.close_date) as integer)  as sales_year,
        o.term_months,
        ol.is_recurring,
        ol.quantity,
        ol.unit_price,
        ol.line_amount
    from opp_lines ol
    inner join opportunities o on ol.opportunity_id = o.opportunity_id
    left join products p on ol.product_id = p.product_id
    left join users u on o.owner_id = u.user_id
),

measures as (
    select
        *,
        -- recurring lines carry their annual recurring amount in line_amount;
        -- one-time lines carry the full fee.
        case when is_recurring then line_amount else 0 end as annual_recurring_amount,
        case when not is_recurring then line_amount else 0 end as one_time_amount,
        line_amount as acv,
        case
            when is_recurring then line_amount * (term_months / 12.0)
            else line_amount
        end as tcv
    from joined
),

-- Account / product history, computed over *won* deals only, to classify motions.
history as (
    select
        *,
        min(case when is_won then close_date end)
            over (partition by account_id) as account_first_won_date,
        min(case when is_won then close_date end)
            over (partition by account_id, product_id) as product_first_won_date
    from measures
)

select
    opportunity_line_id,
    opportunity_id,
    account_id,
    owner_id,
    opportunity_owner,
    sales_region,
    sales_team,
    product_id,
    product_name,
    line_of_business,
    product_family,
    opportunity_type,
    stage_name,
    forecast_category,
    is_closed,
    is_won,
    (is_closed and is_won) as is_closed_won,
    close_date,
    sales_year,
    term_months,
    is_recurring,
    quantity,
    unit_price,
    annual_recurring_amount,
    one_time_amount,
    acv,
    tcv,
    case
        when opportunity_type = 'Churn'      then 'churn'
        when opportunity_type = 'Downgrade'  then 'downgrade'
        when opportunity_type = 'Renewal'    then 'scheduled'
        when is_won and close_date = account_first_won_date then 'new_logo'
        when is_won and close_date = product_first_won_date then 'cross_sell'
        when is_won then 'upsell'
        -- open pipeline: classify by intent
        when opportunity_type = 'New Business' then 'new_logo'
        else 'upsell'
    end as revenue_category
from history
