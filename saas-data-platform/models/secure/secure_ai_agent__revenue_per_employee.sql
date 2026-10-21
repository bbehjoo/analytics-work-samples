{{ config(schema='secure_ai_agent', alias='revenue_per_employee') }}

-- Company-wide ARR per employee for the AI agent. Aggregates only.
select * from {{ ref('rpt_people__revenue_per_employee') }}
