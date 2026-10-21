/*
    rpt_people__revenue_per_employee
    --------------------------------
    One row per month-end: company ARR, company headcount, and ARR per employee.
    The one number that joins the two domains, and the efficiency question every
    hiring plan should answer. Company-wide counts, so nothing to suppress.
*/

with arr as (
    select measurement_month as month_end, sum(ending_arr) as ending_arr
    from {{ ref('fct_arr') }}
    group by 1
),

headcount as (
    select month_end, sum(headcount) as headcount
    from {{ ref('fct_headcount_monthly') }}
    group by 1
)

select
    h.month_end,
    a.ending_arr,
    h.headcount,
    round(a.ending_arr / h.headcount, 0)   as arr_per_employee
from headcount h
join arr a on a.month_end = h.month_end
