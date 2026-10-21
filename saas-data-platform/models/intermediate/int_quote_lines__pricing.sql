{{
  config(materialized='view')
}}

/*
    int_quote_lines__pricing
    ------------------------
    Grain: one row per quote line. The list-to-net price build-up for every
    product on every quote: list amount, discount amount, net amount, plus the
    price book's list price for the same region and year, so pricing integrity
    can be tested (a quote should never invent its own list price).
*/

with lines as (
    select * from {{ ref('stg_salesforce__quote_lines') }}
),

quotes as (
    select * from {{ ref('stg_salesforce__quotes') }}
),

opportunities as (
    select opportunity_id, opportunity_type, close_date, is_closed, is_won
    from {{ ref('stg_salesforce__opportunities') }}
),

books as (
    select * from {{ ref('stg_salesforce__price_books') }}
),

entries as (
    select * from {{ ref('stg_salesforce__price_book_entries') }}
)

select
    l.quote_line_id,
    l.quote_id,
    q.opportunity_id,
    q.account_id,
    q.owner_id,
    l.product_id,
    q.is_primary,
    q.quote_status,
    q.quote_date,
    o.opportunity_type,
    o.close_date,
    o.is_won,
    b.region                                        as price_book_region,
    l.quantity,
    l.is_recurring,
    l.term_months,
    l.list_unit_price,
    e.list_unit_price                               as price_book_list_price,
    l.net_unit_price,
    l.discount_pct,
    l.quantity * l.list_unit_price                  as list_amount,
    l.net_total                                     as net_amount,
    l.quantity * l.list_unit_price - l.net_total    as discount_amount
from lines l
inner join quotes q on l.quote_id = q.quote_id
left join opportunities o on q.opportunity_id = o.opportunity_id
left join books b on q.price_book_id = b.price_book_id
left join entries e
  on e.price_book_id = q.price_book_id
 and e.product_id = l.product_id
 and e.effective_year = cast(extract(year from o.close_date) as integer)
