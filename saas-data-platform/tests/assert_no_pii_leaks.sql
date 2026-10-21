{{ config(group='people') }}  {# owned by People Analytics, so it may read the private dim_employee #}
-- Proof test: no person-level value leaks through a secure view.
--   * every masked, pseudonymized, banded or flagged value differs from the raw value
--   * every column the policy hides is really absent from the view
-- Driven by the column tags and seeds/governance/access_policy.csv, so a new
-- role or a new column is covered without touching this file.
-- Returns one row per leak (expected: 0).
-- depends_on: {{ ref('dim_employee') }}
-- depends_on: {{ ref('secure_hr__employees') }}
-- depends_on: {{ ref('secure_finance__employees') }}
-- depends_on: {{ ref('secure_sales_manager_emea__employees') }}
-- depends_on: {{ ref('secure_analyst__employees') }}
{%- set policy = access_policy() -%}
{%- set cols = governed_columns('dim_employee') -%}
{%- set checks = [] -%}

{%- for role, model_name in secure_employee_views() -%}
    {%- set view = ref(model_name) -%}
    {%- set hidden = [] -%}
    {%- for col in cols -%}
        {%- set t = treatment_for(policy, col, role) -%}
        {%- if t in ('mask', 'pseudonymize', 'band', 'flag') -%}
            {%- do checks.append(
                "select '" ~ role ~ "' as role, '" ~ col.name ~ "' as column_name, "
                ~ "'raw value visible' as problem, cast(v." ~ col.name ~ " as varchar) as value "
                ~ "from " ~ view ~ " v where cast(v." ~ col.name ~ " as varchar) in "
                ~ "(select cast(" ~ col.name ~ " as varchar) from " ~ ref('dim_employee')
                ~ " where " ~ col.name ~ " is not null)") -%}
        {%- elif t == 'hide' -%}
            {%- do hidden.append("'" ~ col.name ~ "'") -%}
        {%- endif -%}
    {%- endfor -%}
    {%- if hidden -%}
        {%- do checks.append(
            "select '" ~ role ~ "', column_name, 'hidden column present', null "
            ~ "from information_schema.columns where table_schema = '" ~ view.schema
            ~ "' and table_name = '" ~ view.identifier ~ "' and lower(column_name) in ("
            ~ hidden | join(', ') ~ ")") -%}
    {%- endif -%}
{%- endfor %}

{% if checks -%}
{{ checks | join('\nunion all\n') }}
{%- else -%}
select null as role, null as column_name, null as problem, null as value where 1 = 0
{%- endif %}
