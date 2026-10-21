{{ config(schema='secure_ai_agent', alias='department_summary') }}

-- The AI agent gets no person-level rows (every category is "hide" for it in
-- access_policy.csv). It answers people questions from suppressed aggregates only.
select * from {{ ref('rpt_people__department_summary') }}
