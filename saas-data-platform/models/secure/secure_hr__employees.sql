{{ config(schema='secure_hr', alias='employees') }}

-- The hr view of dim_employee. Every column and row rule comes from
-- seeds/governance/access_policy.csv and roles.csv; nothing is written by hand.
{{ secure_view('dim_employee', 'hr') }}
