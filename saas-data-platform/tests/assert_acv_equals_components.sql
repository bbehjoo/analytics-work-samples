-- Proof test: ACV must equal annual recurring + frontloaded one-time on every
-- opportunity line (the definition used in int_opportunity_lines__acv).
-- Returns any violating line (expected: 0 rows).
select
    acv_key,
    acv,
    annual_recurring_amount,
    one_time_amount
from {{ ref('fct_acv') }}
where abs(acv - (annual_recurring_amount + one_time_amount)) > 0.01
