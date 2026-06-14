/*
    fct_acv  —  Annual Contract Value (sales performance & pipeline)
    --------------------------------------------------------------
    Grain: one row per opportunity line item (open pipeline + closed deals).

    The sales-motion fact: what did we sell / are we selling, by close date.
    `acv` = average annual recurring + frontloaded one-time; `tcv` = total
    contract value. Includes one-time fees (unlike ARR). Filter `is_closed_won`
    for bookings; filter `not is_closed` for pipeline. Each line carries a
    revenue category (new_logo / cross_sell / upsell / downgrade / scheduled /
    churn) for win/loss and motion analysis.
*/

with acv_lines as (
    select * from {{ ref('int_opportunity_lines__acv') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['opportunity_line_id']) }} as acv_key,
    {{ dbt_utils.generate_surrogate_key(['account_id']) }}          as account_key,
    {{ dbt_utils.generate_surrogate_key(['product_id']) }}          as product_key,
    {{ dbt_utils.generate_surrogate_key(['owner_id']) }}            as sales_rep_key,

    opportunity_line_id,
    opportunity_id,
    account_id,
    product_id,
    owner_id,
    opportunity_owner,
    sales_region,
    sales_team,

    opportunity_type,
    stage_name,
    forecast_category,
    revenue_category,
    is_closed,
    is_won,
    is_closed_won,

    close_date,
    sales_year,
    term_months,
    is_recurring,
    quantity,

    annual_recurring_amount,
    one_time_amount,
    acv,
    tcv
from acv_lines
