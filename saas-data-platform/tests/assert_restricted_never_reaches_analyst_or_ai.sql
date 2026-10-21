{{ config(group='people') }}  {# owned by People Analytics, so it may read the private dim_employee #}
-- Proof test: pay, health and demographic data never reach an analyst or the AI agent.
--   (a) the policy itself allows them nothing but a band (or nothing at all),
--       so an edit to access_policy.csv that loosens this fails the build
--   (b) the analyst sees restricted values only as bands
--   (c) the AI agent's schema has no person-level column at all
-- Returns one row per breach (expected: 0).
-- depends_on: {{ ref('dim_employee') }}
-- depends_on: {{ ref('secure_analyst__employees') }}
-- depends_on: {{ ref('secure_ai_agent__department_summary') }}
{%- set policy = access_policy() -%}
{%- set cols = governed_columns('dim_employee') -%}
{%- set analyst = ref('secure_analyst__employees') -%}
{%- set ai_schema = ref('secure_ai_agent__department_summary').schema -%}
{%- set person_cols = [] -%}
{%- set checks = [] -%}

{%- for col in cols -%}
    {%- if col.sensitivity in ('pii', 'restricted') -%}
        {%- do person_cols.append("'" ~ col.name ~ "'") -%}
    {%- endif -%}
    {%- if col.sensitivity == 'restricted' -%}
        {%- for role in ['analyst', 'ai_agent'] -%}
            {%- set t = treatment_for(policy, col, role) -%}
            {%- if t not in ('hide', 'band') -%}
                {%- do checks.append("select '" ~ role ~ "' as role, '" ~ col.name ~ "' as column_name, "
                    ~ "'policy exposes restricted data as " ~ t ~ "' as problem") -%}
            {%- endif -%}
        {%- endfor -%}
        {%- if treatment_for(policy, col, 'analyst') == 'band' -%}
            {%- do checks.append("select distinct 'analyst', '" ~ col.name ~ "', 'restricted value not banded' "
                ~ "from " ~ analyst ~ " where " ~ col.name ~ " is not null and " ~ col.name ~ " not like '$%k'") -%}
        {%- endif -%}
    {%- endif -%}
{%- endfor -%}

{%- do checks.append("select 'ai_agent', column_name, 'person-level column in AI schema' "
    ~ "from information_schema.columns where table_schema = '" ~ ai_schema ~ "' "
    ~ "and lower(column_name) in (" ~ person_cols | join(', ') ~ ")") %}

{{ checks | join('\nunion all\n') }}
