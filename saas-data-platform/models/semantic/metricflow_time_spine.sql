{{ config(materialized='table') }}

-- Daily time spine required by the dbt Semantic Layer / MetricFlow to align
-- metrics to a common time axis and fill date gaps.
with days as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2022-01-01' as date)",
        end_date="cast('2027-01-01' as date)"
    ) }}
)

select cast(date_day as date) as date_day
from days
