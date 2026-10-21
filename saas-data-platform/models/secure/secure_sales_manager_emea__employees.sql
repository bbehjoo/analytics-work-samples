{{ config(schema='secure_sales_manager_emea', alias='employees') }}

-- The sales_manager_emea view of dim_employee. Every column and row rule comes from
-- seeds/governance/access_policy.csv and roles.csv; nothing is written by hand.
{{ secure_view('dim_employee', 'sales_manager_emea') }}
