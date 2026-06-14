-- Proof test: company ARR is continuous month to month, i.e. the ending ARR of
-- one month equals the beginning ARR of the next. Returns any break (expected: 0).
with monthly as (
    select
        measurement_month,
        sum(ending_arr)    as ending_arr,
        sum(beginning_arr) as beginning_arr
    from {{ ref('fct_arr') }}
    group by 1
),

sequenced as (
    select
        measurement_month,
        ending_arr,
        lead(beginning_arr) over (order by measurement_month) as next_month_beginning_arr
    from monthly
)

select *
from sequenced
where next_month_beginning_arr is not null
  and abs(ending_arr - next_month_beginning_arr) > 0.01
