-- Proof test (closed loop): the reconciliation mart must surface exactly the
-- discrepancies the generator seeded (see scripts/seeded_discrepancy_counts.json).
-- Returns any category whose count drifts from the seeded value (expected: 0 rows).
with expected (discrepancy_category, expected_count) as (
    values
        ('amount_mismatch', 15),
        ('partially_invoiced', 12),
        ('timing_difference', 10),
        ('missing_in_netsuite', 8),
        ('currency_rounding', 6),
        ('orphan_in_netsuite', 5)
),

actual as (
    select discrepancy_category, count(*) as actual_count
    from {{ ref('rpt_contract_to_netsuite_recon') }}
    group by 1
)

select
    e.discrepancy_category,
    e.expected_count,
    coalesce(a.actual_count, 0) as actual_count
from expected e
left join actual a on e.discrepancy_category = a.discrepancy_category
where e.expected_count <> coalesce(a.actual_count, 0)
