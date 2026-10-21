{{ config(schema='secure_analyst', alias='employees') }}

-- The analyst view of dim_employee. Every column and row rule comes from
-- seeds/governance/access_policy.csv and roles.csv; nothing is written by hand.
{{ secure_view('dim_employee', 'analyst') }}
