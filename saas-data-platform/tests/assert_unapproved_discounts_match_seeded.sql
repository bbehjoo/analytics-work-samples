-- Proof test (closed loop): the approvals check finds exactly the deals the
-- generator closed above the discount threshold without an approval
-- (scripts/seeded_cpq_findings.json). Too few means the check is missing some;
-- too many means approvals are being lost. Returns a row on any drift (expected: 0).
with actual as (
    select count(*) as unapproved
    from {{ ref('fct_quote') }}
    where requires_approval and not is_approved
)

select unapproved, 9 as expected
from actual
where unapproved <> 9
